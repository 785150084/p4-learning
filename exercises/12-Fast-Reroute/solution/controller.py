"""A central controller computing and installing shortest paths.

In case of a link failure, paths are recomputed.
"""

import os
from networkx.algorithms import all_pairs_dijkstra

from p4utils.utils.topology import Topology
from p4utils.utils.sswitch_API import SimpleSwitchAPI

from cli import CLI


class RerouteController(object):
    """Controller for the fast rerouting exercise."""

    def __init__(self):
        """Initializes the topology and data structures."""

        if not os.path.exists("topology.db"):
            print "Could not find topology object!\n"
            raise Exception

        self.topo = Topology(db="topology.db")
        self.controllers = {}
        self.connect_to_switches()
        self.reset_states()

        # Preconfigure all MAC addresses
        self.install_macs()

        # Install nexthop indices and populate registers.
        self.install_nexthop_indices()
        self.update_nexthops()

    def connect_to_switches(self):
        """Connects to all the switches in the topology."""
        for p4switch in self.topo.get_p4switches():
            thrift_port = self.topo.get_thrift_port(p4switch)
            self.controllers[p4switch] = SimpleSwitchAPI(thrift_port)

    def reset_states(self):
        """Resets registers, tables, etc."""
        for control in self.controllers.values():
            control.reset_state()

    def install_macs(self):
        """Install the port-to-mac map on all switches.

        You do not need to change this.

        Note: Real switches would rely on L2 learning to achieve this.
        """
        for switch, control in self.controllers.items():
            print "Installing MAC addresses for switch '%s'." % switch
            print "=========================================\n"
            for neighbor in self.topo.get_neighbors(switch):
                mac = self.topo.node_to_node_mac(neighbor, switch)
                port = self.topo.node_to_node_port_num(switch, neighbor)
                control.table_add('rewrite_mac', 'rewriteMac',
                                  [str(port)], [str(mac)])

    def install_nexthop_indices(self):
        """Install the mapping from prefix to nexthop ids for all switches."""
        for switch, control in self.controllers.items():
            print "Installing nexthop indices for switch '%s'." % switch
            print "===========================================\n"
            control.table_clear('ipv4_lpm')
            for host in self.topo.get_hosts():
                subnet = self.get_host_net(host)
                index = self.get_nexthop_index(host)
                control.table_add('ipv4_lpm', 'read_port',
                                  [subnet], [str(index)])

    def get_host_net(self, host):
        """Return ip and subnet of a host.

        Args:
            host (str): The host for which the net will be retruned.

        Returns:
            str: IP and subnet in the format "address/mask".
        """
        gateway = self.topo.get_host_gateway_name(host)
        return self.topo[host][gateway]['ip']

    def get_nexthop_index(self, host):
        """Return the nexthop index for a destination.

        Args:
            host (str): Name of destination node (host).

        Returns:
            int: nexthop index, used to look up nexthop ports.
        """
        # For now, give each host an individual nexthop id.
        host_list = sorted(list(self.topo.get_hosts().keys()))
        return host_list.index(host)

    def get_port(self, node, nexthop_node):
        """Return egress port for nexthop from the view of node.

        Args:
            node (str): Name of node for which the port is determined.
            nexthop_node (str): Name of node to reach.

        Returns:
            int: nexthop port
        """
        return self.topo.node_to_node_port_num(node, nexthop_node)

    def failure_notification(self, failures):
        """Called if a link fails.

        Args:
            failures (list(tuple(str, str))): List of failed links.
        """
        self.update_nexthops(failures=failures)

    # Helpers to update nexthops.
    # ===========================

    def dijkstra(self, failures=None):
        """Compute shortest paths and distances.

        Args:
            failures (list(tuple(str, str))): List of failed links.

        Returns:
            tuple(dict, dict): First dict: distances, second: paths.
        """
        graph = self.topo.network_graph

        if failures is not None:
            graph = graph.copy()
            for failure in failures:
                graph.remove_edge(*failure)

        # Compute the shortest paths from switches to hosts.
        dijkstra = dict(all_pairs_dijkstra(graph, weight='weight'))

        distances = {node: data[0] for node, data in dijkstra.items()}
        paths = {node: data[1] for node, data in dijkstra.items()}

        return distances, paths

    def compute_nexthops(self, failures=None):
        """Compute the best nexthops for all switches to each host.

        Optionally, a link can be marked as failed. This link will be excluded
        when computing the shortest paths.

        Args:
            failures (list(tuple(str, str))): List of failed links.

        Returns:
            dict(str, list(str, str, int))):
                Mapping from all switches to subnets, MAC, port.
        """
        # Compute the shortest paths from switches to hosts.
        all_shortest_paths = self.dijkstra(failures=failures)[1]

        # Translate shortest paths to mapping from host to nexthop node
        # (per switch).
        results = {}
        for switch in self.controllers:
            switch_results = results[switch] = []
            for host in self.topo.network_graph.get_hosts():
                try:
                    path = all_shortest_paths[switch][host]
                except KeyError:
                    print "WARNING: The graph is not connected!"
                    print "'%s' cannot reach '%s'." % (switch, host)
                    continue
                nexthop = path[1]  # path[0] is the switch itself.
                switch_results.append((host, nexthop))

        return results

    # Update nexthops.
    # ================

    def update_nexthops(self, failures=None):
        """Install nexthops in all switches."""
        nexthops = self.compute_nexthops(failures=failures)
        lfas = self.compute_lfas(nexthops, failures=failures)

        for switch, destinations in nexthops.items():
            print "Updating nexthops for switch '%s'." % switch
            control = self.controllers[switch]
            for host, nexthop in destinations:
                nexthop_id = self.get_nexthop_index(host)
                port = self.get_port(switch, nexthop)
                # Write the port in the nexthop lookup register.
                control.register_write('primaryNH', nexthop_id, port)

        #######################################################################
        # Compute loop-free alternate nexthops and install them below.
        #######################################################################

            # LFA solution.
            # =============
            print "Installing LFAs."
            print "----------------"

            for host, nexthop in destinations:
                nexthop_id = self.get_nexthop_index(host)
                if host == nexthop:
                    continue  # Cannot do anything if host link fails.

                try:
                    lfa_nexthop = lfas[switch][host]
                except KeyError:
                    print "WARNING: No LFA from %s to %s " % (switch, host) + \
                          "if %s is not available!" % (nexthop)
                    lfa_nexthop = nexthop  # Fallback to default nh.

                lfa_port = self.get_port(switch, lfa_nexthop)
                control.register_write('alternativeNH', nexthop_id, lfa_port)

    def compute_lfas(self, nexthops, failures=None):
        """Compute LFA (loop-free alternates) for all nexthops."""
        _d = self.dijkstra(failures=failures)[0]
        lfas = {}
        for switch, destinations in nexthops.items():
            switch_lfas = lfas[switch] = {}
            connected = set(self.topo.get_switches_connected_to(switch))
            for host, nexthop in destinations:
                if nexthop == host:
                    continue  # Nothing can be done if host link fails.

                others = connected - {nexthop}
                # Check with alternates are loop free
                noloop = []
                for alternate in others:
                    # The following condition needs to hold:
                    # D(N, D) < D(N, S) + D(S, D)
                    if (_d[alternate][host]
                            < _d[alternate][switch] + _d[switch][host]):
                        total_dist = _d[switch][alternate] + \
                            _d[alternate][host]
                        noloop.append((alternate, total_dist))

                    if not noloop:
                        continue  # No LFA :(

                    # Keep LFA with shortest distance
                    switch_lfas[host] = min(noloop, key=lambda x: x[1])[0]

        return lfas


if __name__ == "__main__":
    controller = RerouteController()  # pylint: disable=invalid-name
    CLI(controller)
