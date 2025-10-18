# Linux Pressure Stall Information (PSI) Status App
`psistat` is a simple python3 program to display the PSIs and to capture/display exception events.  See [PSI - Pressure Stall Information — The Linux Kernel documentation](https://docs.kernel.org/accounting/psi.html) for more information.

`psistat` might be found helpful when encountering unexplained system delays and you wish to identify the general cause.  Regularly occuring high PSIs may indicate the system is undersized or overloaded, and, if warranted, implementing automated load-shedding.  

## Installation
Download the `psistat` program, make it excutable, and put in on your execution path.
For example, this might suffice for your install:
```
    git clone git@github.com:joedefen/psistat.git
    chmod +x psistat/psistat
    cp psistat/psistat ~/.local/bin/.
    rm -rf psistat
```

## Instruction for Use
Typically, simply run `psistat`.  Its window looks like:

```
TBD
```

`psistat` displays:
* On the top portion of the screen, the 1s, 3s, and 10s PSI stats (each is a percent stalled during the interval).
* Below the stats is a list of exception events beginning with the most recent;
  each event includes:
  * The relative time and absolution time of the event.
  * The type of event.
  * The pressure value as a percentage relative to the current threshold.


When `psistat` is running, entering these keys has special effect:
* `j` - lower the threshold for exception events by 5% (but to no lower than 5%)
* `k` - raise the threshold for exception events by 5% (but to no higher than 95%)
* `q` - quit the program.


`psistat` has only a few options:
```
usage: psistat [-h] [-D] [-t THRESHOLD_PCT]

optional arguments:
  -h, --help            show this help message and exit
  -D, --debug           debug mode w/o Window
  -t THRESHOLD_PCT, --threshold-pct THRESHOLD_PCT
                        event threshold pct [min=5, max=95, dflt=20]
```

## Load Test
To create some test loads, you can use the `create_load.c` program found at
[psi-by-example](https://github.com/shuveb/psi-by-example).

