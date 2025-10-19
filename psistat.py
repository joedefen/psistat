#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2022-2025 Joe Defen

Pressure Stall Indicators (PSI) status program. Shows:
    - 1, 3, and 5 second running averages( in percent) of the 5 PSIs
    - the recent history of PSI events that are defined by
      exceeding a threshold percentage in a second.
      
Now uses the 'console-window' library for the TUI interface.
"""

# pylint: disable=invalid-name,too-many-instance-attributes,import-outside-toplevel,broad-except,too-many-locals

import sys
import os
import time
import re
import traceback
from datetime import datetime
from types import SimpleNamespace
import curses as cs
import locale
from types import SimpleNamespace
from console_window import ConsoleWindow, OptionSpinner

locale.setlocale(locale.LC_ALL, '') # needed to draw unicode chars


SAMPLES = 11
BILLION = 1000000000

##############################################################################
##  Turn time differences in seconds to a compact representation;
##  e.g., '18h·39m'
##############################################################################
def ago_str(delta_secs):
    """Prints a 6-character string (max) the represents how long
    ago (i.e., delta_secs) is briefly."""
    ago = int(max(0, round(delta_secs if delta_secs >= 0 else -delta_secs)))
    divs = (60, 60, 24, 7, 52, 9999999)
    units = ('s', 'm', 'h', 'd', 'w', 'y')
    vals = (ago%60, int(ago/60)) # seed with secs, mins (step til 2nd fits)
    uidx = 1 # best units
    for div in divs[1:]:
        if vals[1] < div:
            break
        vals = (vals[1]%div, int(vals[1]/div))
        uidx += 1
    rv = '{:d}{}'.format(vals[1], units[uidx]) if vals[1] else ''
    fmt = '{:02d}{}' if vals[1] else '{:2d}{}'
    rv += fmt.format(vals[0], units[uidx-1])
    return rv


class PressureGroup:
    """Handler for one PSI group (i.e., cpu, io, or memory)
    """
    pattern = re.compile(r'^(\S+)\b.*\bavg60=(\d+\.\d+)\b.*\bavg300=(\d+\.\d+)\b.*\btotal=(\d+)$')
    def __init__(self, tag, stats):
        self.stats = stats
        self.avgs = {60: 0, 300: 0} # averages from /proc/pressure/{tag}
        self.tag = tag
        self.fullpath = '/proc/pressure/' + tag
        self.handle = open(self.fullpath)
        
    def sample_ns(self):
        """ return the initialized namespace for a sample.
        It includes the list of recent microseconds of pressure samples and
        the averages for 60s and 300s"""
        return SimpleNamespace(micros=[], avgs={60: 0, 300:0})

    def add_sample(self):
        """Read/Parse the /proc/pressure/{group} file"""
        self.handle.seek(0)
        document = self.handle.read()
        allowed_subkeys = {'full', 'some'}
        for line in document.splitlines():
            match = self.pattern.match(line)
            
            # NOTE: Your original regex assumed match was successful. Adding check.
            if not match:
                continue
            subkey, micro = match.group(1), match.group(4)
            avg60, avg300 = match.group(2), match.group(3)
            if subkey not in allowed_subkeys:
                continue
            allowed_subkeys.discard(subkey)
            key = f'{self.tag}.{subkey}'
            ns = self.stats.get(key, None)
            if not ns:
                ns = self.stats[key] = self.sample_ns()
            ns.micros.insert(0, int(micro))
            del ns.micros[SAMPLES:]
            ns.avgs[60], ns.avgs[300] = float(avg60), float(avg300)
        assert not allowed_subkeys, f"{self.fullpath} expecting full+some values"

class PsiStat:
    """Class to display PSI information including
    running averages and exception events"""
    singleton = None
    def __init__(self, threshold=5, brief=False, itvl=10):
        assert self.singleton is None
        PsiStat.singleton = self
        self.next_mono = time.monotonic_ns() # when to sleep to next
        self.stats = { 'cpu.full': None, 'cpu.some': None,
                       'io.full': None, 'io.some': None,
                       'memory.full': None, 'memory.some': None
                     }
        self.monos = []
        self.times = []
        self.psgs = []
        self.events = []
        self.event_floor = {}
        self.lineno = 0 # Not strictly needed with ConsoleWindow, but harmless.
        self.last_sample_mono = 0

        # --- CONSOLE-WINDOW SETUP ---
        # Setup OptionSpinner for 'j' and 'k' keys
        self.spin = OptionSpinner()
        self.opts = self.spin.default_obj
        self.spin.add_key('help_mode', '? - toggle help screen', vals=[False, True])
        self.spin.add_key(attr='event_interval', descr='i - event interval (secs)',
                  vals=[10, 3, 1, 300, 60])
        self.spin.add_key(attr='threshold', descr='t - set event threshold percent [1,99]',
                          prompt="Enter event threshold percent in range [1,99]")
        self.spin.add_key(attr='brief', descr='b - only load events that fit on screen',
                  vals=['off', 'on'])
        self.spin.add_key(attr='dump_now', descr='d - dump event log now',
                  vals=[False, True])
        self.spin.add_key(attr='quit', descr='q or CTRL-c - quit program',
                  vals=[False, True])

        # FIXME: keys
        others = ''
        other_keys = set(ord(x) for x in others)
        # other_keys.add(cs.KEY_ENTER)
        # other_keys.add(27) # ESCAPE
        # other_keys.add(10) # another form of ENTER
        self.opts.brief = 'on' if brief else 'off'
        self.opts.threshold = threshold
        self.opts.event_interval = itvl

        # Initialize ConsoleWindow
        self.window = ConsoleWindow(head_line=True, keys=self.spin.keys^other_keys)

        for tag in 'cpu', 'io', 'memory':
            self.psgs.append(PressureGroup(tag, self.stats))


    def dump_event_log(self, do_return=False):
        """  drop out of Window and dump the events """
        if self.window:
            self.window.stop_curses()
        os.system('clear; stty sane')
        for event in reversed(self.events):
            print(event[1])
        if do_return:
            os.system(r' /bin/echo -e "\n\n===== Press ENTER to return to psistat ====> \c"; read FOO')
            if self.window:
                self.window._start_curses()


    def prc_samples(self, valid_sample_count):
        """Show the current PSI stats/events using the
        most recent samples while also detecting new events
        for exceptional samples. Then show the recent events.
        """
        # Access threshold from OptionSpinner object
        threshold = self.opts.threshold
        itvl = self.opts.event_interval
        brief = self.opts.brief
        dt_object = datetime.fromtimestamp(time.time())
        hhmmss = dt_object.strftime("%H:%M:%S")

        title = f'PSIs {hhmmss} | [t]hresh={threshold}% [i]tvl={itvl}s [b]rief={brief} [d]ump ?:help [q]uit'
        self.window.add_header(title)

        # Draw Header
        header = (f' {"1s":->5} {"3s":->5} {"10s":->5} {"60s":->5} {"300s":->5}  {"Full.Stall%":>11}'
                  + f'      {"1s":->5} {"3s":->5} {"10s":->5} {"60s":->5} {"300s":->5}  {"Some.Stall%":>11}')
        self.window.add_header(header) 
        
        # --- Draw PSI Stats ---
        line, event, specifically = '', '', ''
        now = time.time()
        for idx, key in enumerate(self.stats):
            micros = self.stats[key].micros
            del micros[valid_sample_count:]
            avgs = self.stats[key].avgs
            
            for ii in (1, 3, 10, 60, 300):
                if ii in (1, 3, 10):
                    if len(micros) <= ii:
                        line += ' ' + 'n/a'.rjust(5)
                        continue

                    delta_micros = (micros[0] - micros[ii])
                    delta_monos = (self.monos[0] - self.monos[ii])
                    
                    # Avoid division by zero if delta_monos is unexpectedly zero
                    if delta_monos == 0:
                        pct = 0.0
                    else:
                        pct = 100 * 1000 * delta_micros / delta_monos
                    
                else:
                    pct = avgs.get(ii, 0.0)
                
                line += f' {pct:5.1f}'

                # detect/collect the 1s samples that exceed the threshold
                floor_key = f'{key}.{ii}'
                floor = self.event_floor.get(floor_key, 0)
                if ii == itvl and round(pct, 2) >= threshold and now >= floor:
                    if not event:
                        dt_object = datetime.fromtimestamp(now)
                            # Truncate microseconds to milliseconds (.mmm) with [:-3]
                        event += dt_object.strftime("%m-%d %H:%M:%S.%f")[:-3]

                    specifically = f'{pct:7.1f}% {key:<11s}'
                    if '.full' not in event and '.some' in key:
                        event += '  ' + '.' * len(specifically)
                    event += '  ' + specifically
                    self.event_floor[floor_key] = now + itvl
            line += f'  {key:<11}'

            if idx % 2 == 0:
                line += '     '
            else:
                if not self.opts.help_mode:
                    self.window.add_header(line)
                line = ''
                if event:
                    if '.some' not in event and '.full' in key:
                        event += '  ' + '.' * len(specifically)
                    event += f'   >={threshold}% i={itvl}s'
                    self.events.insert(0, (time.monotonic_ns(), event))
                    event = ''
            
        del self.events[1000:]
        
        # --- Draw Events ---
        if not self.opts.help_mode:
            self.window.calc()
            limit = (self.window.rows - self.window.body_base) if self.opts.brief == 'on' else 200
            for idx, event in enumerate(self.events):
                if idx >= limit:
                    break
                mono_ns, descr = event
                ago = ago_str((time.monotonic_ns() - mono_ns)/BILLION).strip()
                self.window.put_body(f'{idx:03d} {ago:>6s}: {descr}')
            
    def show_help_screen(self):
        """ TBD """
        self.window.clear()
        self.window.set_pick_mode(False)
        self.spin.show_help_nav_keys(self.window)
        self.spin.show_help_body(self.window)
        lines = [
            '   CTRL-c - quit program'
        ]
        for line in lines:
            self.window.put_body(line)
            
    def count_valid_samples(self):
        """ Valid samples are no worse that 1.25s later than the one before
         and no more than SAMPLES """
        # return SAMPLES-1
        count = 1
        del self.monos[SAMPLES:]
        for loop in range(0, len(self.monos) - 1):
            delta_ns = self.monos[loop] - self.monos[loop+1]
            if  delta_ns > 1000000000 * 1.25:
                break
            count += 1
        return count
 
    def process_psgs(self):
        """ TBD """
        for psg in self.psgs:
            psg.add_sample()
            
        self.times.insert(0, time.time())
        mono = time.monotonic_ns()
        self.monos.insert(0, mono)
        valid_sample_count = self.count_valid_samples()
        del self.monos[valid_sample_count:]
        del self.times[valid_sample_count:]

        if not self.opts.help_mode:
            self.window.clear()
            
        self.prc_samples(valid_sample_count)


    def loop(self):
        """Do one loop of collecting samples, and then displaying running
        averages and exception events."""
        timeout_secs, min_timout_secs = 1.0, 0.9
        
        if time.monotonic() - self.last_sample_mono >= min_timout_secs:
            self.process_psgs()
            self.last_sample_mono = time.monotonic()

        if self.opts.help_mode:
            self.show_help_screen()
        
        # --- CONSOLE-WINDOW LOOP INTEGRATION ---
        
        # Render the screen
        self.window.render()
        sleep_secs = timeout_secs - (time.monotonic() - self.last_sample_mono)
        
        # Wait for input/timeout using ConsoleWindow.prompt()
        keystroke = self.window.prompt(seconds=sleep_secs)
        
        if keystroke is not None:
            # Pass key to OptionSpinner for handling 'j' and 'k'
            if self.spin.do_key(keystroke, self.window):
                if isinstance(self.opts.threshold, str):
                    try:
                        self.opts.threshold = int(self.opts.threshold)
                        if self.opts.threshold < 1:
                            self.opts.threshold = 1
                        elif self.opts.threshold > 99:
                            self.opts.threshold = 99
                    except Exception:
                        self.opts.threshold = 999999
                if self.opts.dump_now:
                    self.dump_event_log(do_return=True)
                    self.opts.dump_now = False
                if self.opts.quit:
                    sys.exit(0)

                return True 
            if keystroke in (ord('q'), ord('Q')):
                return False # Quit
                
        # The loop continues after timeout or non-threshold keystroke
        return True

def main():
    try:
        """Main execution function, handles CLI arguments."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('-b', '--brief', action='store_true',
                            help='whether present only as meny events as fit on the screen')
        parser.add_argument('-i', '--event-interval', default=10, type=int, choices=[1,3,10,60,300],
                            help='average interval used for events')
        parser.add_argument('-t', '--threshold-pct', default=5, type=int,
                            help='event threshold percent [1-99,dflt=5]')
        opts = parser.parse_args()
        
        pct = min(max(opts.threshold_pct, 1), 99)

        pstall = PsiStat(threshold=pct, brief=opts.brief, itvl=opts.event_interval)

        while pstall.loop():
            pass

    except Exception as exc:
        # Note: We no longer call Window.exit_handler(), as ConsoleWindow handles it
        # and there is no guarantee the Window class was ever initialized.
        if PsiStat.singleton and PsiStat.singleton.window:
            PsiStat.singleton.window.stop_curses()

        print("exception:", str(exc))
        print(traceback.format_exc())

if __name__ == '__main__':

    main()
