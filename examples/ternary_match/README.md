# Ternary Match Example

```
+----+       +----+         +----+
| h1 +-------+ s1 +---------+ h2 |
+----+       +----+         +----+
```

# Introduction

Very simple forwarding program that uses a ternary match. See `s1-commands.txt` to see
how to populate tables with ternary matches using the CLI API. You will see that matches are
of the form `value&mask`, for example: `0x00000000&&&0x80000000`, and the last action parameter
is used as priority (lower better).

# How to run

To start the topology with the P4 switches:

```
sudo p4run
```

You can send packets and set different destination ip addresses to play with the program.

```
mx h1
python send.py
```