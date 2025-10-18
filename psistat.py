#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2022-2025 Joe Defen

Pressure Stall Indicators (PSI) status program. Shows:
    - 1, 3, and 5 second running averages( in percent) of the 5 PSIs
    - the recent history of PSI events that are defined by
      exceeding a threshold percentage in a second.
      
Now uses the 'console-window' library for the TUI interface.

TODO List:
  -- add spinner to change the event interval; start with 10 (allow 3 and 1)
  -- add cooldown period after event (10, 3, 1)
  -- add dump key to drop out of curses, dump the known events, prompt to return to curses
  -- add automatic dump on end of program
  -- put the keys and current values on the first line + the current HH:SS
  -- update install in README (to pipx), show new look, show new options/keys,
     show new CLI options
  -- create .toml and structure for publish to pypi.org
  -- advertise psistat on r/linux
"""

# pylint: disable=invalid-name,too-many-instance-attributes,import-outside-toplevel,broad-except,too-many-locals

import sys
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
    rv = '{:d}{}'.format(vals[1], units[uidx]) if vals[1] else '    '
    rv += '{:d}{}'.format(vals[0], units[uidx-1])
    return rv


class PressureGroup:
    """Handler for one PSI group (i.e., cpu, io, or memory)
    """
    pattern = re.compile(r'^(\S+)\b.*\bavg60=(\d+\.\d+)\b.*\bavg300=(\d+\.\d+)\b.*\btotal=(\d+)$')
    def __init__(self, debug, tag, stats):
        self.DB = debug
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
            if self.DB:
                print('DB:', self.tag, line)
            
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
    def __init__(self, debug=True, threshold=20):
        self.DB = debug
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

        # --- CONSOLE-WINDOW SETUP ---
        if not self.DB:
            # Setup OptionSpinner for 'j' and 'k' keys
            self.spin = OptionSpinner()
            self.opts = self.spin.default_obj
            self.spin.add_key('help_mode', '? - toggle help screen', vals=[False, True])
            self.spin.add_key(attr='event_interval', descr='i - event interval',
                      vals=[10, 3, 1, 300, 60])
            self.spin.add_key(attr='threshold', descr='T - raise threshold',
                      vals=list(range(5, 100, 5))) # 5, 10, 15, ..., 95)
            self.spin.add_key(attr='lower_threshold', descr='t - lower threshold now',
                      vals=[False, True])
            self.spin.add_key(attr='dump_now', descr='d - dump event log now',
                      vals=[False, True])

            # FIXME: keys
            others = ''
            other_keys = set(ord(x) for x in others)
            other_keys.add(cs.KEY_ENTER)
            other_keys.add(27) # ESCAPE
            other_keys.add(10) # another form of ENTER

            # Initialize ConsoleWindow
            self.window = ConsoleWindow(head_line=True, keys=self.spin.keys^other_keys)
        else:
            self.opts = SimpleNamespace(threshold=threshold,
                                        event_interval=10)
            self.window = None

        for tag in 'cpu', 'io', 'memory':
            self.psgs.append(PressureGroup(debug, tag, self.stats))


    def prc_samples(self):
        """Show the current PSI stats/events using the
        most recent samples while also detecting new events
        for exceptional samples. Then show the recent events.
        """
        if self.DB:
            print(self.stats)
        
        # Access threshold from OptionSpinner object
        threshold = self.opts.threshold
        itvl = self.opts.event_interval

        if not self.DB:
            title = f'PSISTAT | [tT]hresh={threshold}% [i]tvl={itvl} [d]ump ?:help'
            self.window.add_header(title)

        # Draw Header
        header = (f' {"1s":->5} {"3s":->5} {"10s":->5} {"60s":->5} {"300s":->5}  {"Full.Stall%":>11}'
                  + f'      {"1s":->5} {"3s":->5} {"10s":->5} {"60s":->5} {"300s":->5}  {"Some.Stall%":>11}')
        # Using add_body here since ConsoleWindow separates header content from title line
        self.window.add_header(header) 
        
        # --- Draw PSI Stats ---
        line, event = '', ''
        now = time.time()
        mono_now = time.monotonic_ns()
        for idx, key in enumerate(self.stats):
            micros = self.stats[key].micros
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
                    
                    if self.DB and delta_micros > 0:
                        print(f'DB: {key} {delta_micros} / {delta_monos} = {pct:.9f}%')
                else:
                    pct = avgs.get(ii, 0.0)
                
                line += f' {pct:5.1f}'

                # detect/collect the 1s samples that exceed the threshold
                floor_key = f'{key}.{ii}'
                floor = self.event_floor.get(floor_key, 0)
                if ii == itvl and round(pct, 3) >= threshold and now >= floor:
                    if not event:
                        dt_object = datetime.fromtimestamp(now)
                            # Truncate microseconds to milliseconds (.mmm) with [:-3]
                        event += dt_object.strftime("%m-%d %H:%M:%S.%f")[:-3]

                    specifically = f' {key:>11s} {pct:7.3f}'
                    if '.full' not in event and '.some' in key:
                        event += ' ' * len(specifically)
                    event += specifically
                    if self.DB:
                        print(event)
                    self.event_floor[floor_key] = now + itvl
            line += f'  {key:<11}'

            if idx % 2 == 0:
                line += '     '
            else:
                self.window.add_header(line)
                line = ''
                if event:
                    event += f'   >={threshold} i={itvl}'
                    self.events.insert(0, (time.monotonic_ns(), event))
                    event = ''
            
        del self.events[100:]
        
        # --- Draw Events ---
        for event in self.events:
            mono_ns, descr = event
            ago = ago_str((time.monotonic_ns() - mono_ns)/BILLION).strip()
            self.window.add_body(f'{ago:>6s}: {descr}')
            
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
            
    def process_psgs(self):
        """ TBD """
        for psg in self.psgs:
            psg.add_sample()
            
        self.times.insert(0, time.time())
        mono = time.monotonic_ns()
        self.monos.insert(0, mono)
        del self.monos[SAMPLES:]
        del self.times[SAMPLES:]

        # Reset and render the screen content
        if not self.DB:
            self.window.clear()
            
        self.prc_samples()

        delta = self.next_mono - mono
        while delta <= 0:
            self.next_mono += BILLION
            delta = self.next_mono - mono
            
        # Time to wait (in milliseconds)
        return int(delta / BILLION * 1000)


    def loop(self):
        """Do one loop of collecting samples, and then displaying running
        averages and exception events."""
        timeout_ms = 1000
        if self.opts.help_mode:
            self.show_help_screen()
        else:
            timeout_ms = self.process_psgs()

        if self.DB:
            time.sleep(delta / BILLION)
            return True # Never quit in DB mode
        
        # --- CONSOLE-WINDOW LOOP INTEGRATION ---
        
        # Render the screen
        self.window.render()
        
        # Wait for input/timeout using ConsoleWindow.prompt()
        keystroke = self.window.prompt(seconds=timeout_ms / 1000.0)
        
        if keystroke is not None:
            # Pass key to OptionSpinner for handling 'j' and 'k'
            if self.spin.do_key(keystroke, self.window):
                if self.opts.lower_threshold:
                    if self.opts.threshold > 10:
                        self.opts.threshold -= 5
                    else:
                        self.opts.threshold = 95
                    self.opts.lower_threshold = False

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
        parser.add_argument('-D', '--debug', action='store_true', help='debug mode w/o Window')
        parser.add_argument('-t', '--threshold-pct', default=20, type=int,
                            help='event threshold pct [min=5, max=95, dflt=20]')
        args = parser.parse_args()
        
        # Calculate nearest multiple of 5 between 5 and 95, preserving original logic
        pct = int(round(args.threshold_pct / 5))*5
        pct = min(max(pct, 5), 95)

        pstall = PsiStat(debug=args.debug, threshold=pct)

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
