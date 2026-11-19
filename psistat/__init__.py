#!/usr/bin/env python3
"""
Copyright (c) 2022-2026 Joe Defen

Pressure Stall Indicators (PSI) status program.  Shows:
    - 1, 3, 10, 60, and 300 second running averages (in percent)
      of the 6 PSI stats (cpu/io/memory x full/some)
    - the recent history of PSI events that are defined
      by exceeding a threshold percentage in a second.
"""

# pylint: disable=invalid-name,too-many-instance-attributes,import-outside-toplevel,broad-except,too-many-locals

__version__ = "1.2.2" # The single source of the release number

import argparse
import curses as cs
import locale
import os
import re
import sys
import time
import traceback
from datetime import datetime
from types import SimpleNamespace

from console_window import (
    BasicHelpScreen,
    ConsoleWindow,
    ConsoleWindowOpts,
    HeaderLine,
    OptionSpinner,
    Screen,
    ScreenStack,
    TerminalTooSmallError,
)

locale.setlocale(locale.LC_ALL, '') # needed to draw unicode chars

ConsoleWindow.timeout_ms = 100 # Poll in short slices so prompt() returns close to `seconds`.

SAMPLES = 11
BILLION = 1000000000

# Screen numbers, in the order the ScreenStack numbers them: the report is home.
REPORT_ST = 0
HELP_ST = 1

# The two half-columns of the stats band.
STAT_COLS = f' {"1s":->6} {"3s":->6} {"10s":->6} {"60s":->6} {"300s":->6}'
STAT_HEADER = f'{STAT_COLS}  {"Full%":<6}     {STAT_COLS}  {"Some%":<6}'


# #############################################################################
# # Turn delta secs to a compact representation; # e.g., '18h·39m'
# #############################################################################
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
    rv = f'{vals[1]:d}{units[uidx]}' if vals[1] else ''
    fmt = '{:02d}{}' if vals[1] else '{:2d}{}'
    rv += fmt.format(vals[0], units[uidx-1])
    return rv


def check_threshold(answer):
    """``check_ans`` callback for the threshold prompt."""
    try:
        value = int(str(answer))
    except ValueError:
        return 'want a whole number in [1,99]'
    if not 1 <= value <= 99:
        return 'want a whole number in [1,99]'
    return None


class PressureGroup:
    """Handler for one PSI group (i.e., cpu, io, or memory)"""
    pattern = re.compile(r'^(\S+)\b.*\bavg60=(\d+\.\d+)\b.*\bavg300=(\d+\.\d+)\b.*\btotal=(\d+)$')
    def __init__(self, tag, stats):
        self.stats = stats
        self.avgs = {60: 0, 300: 0} # averages from /proc/pressure/{tag}
        self.tag = tag
        self.fullpath = '/proc/pressure/' + tag
        # The sampler holds this reader for the process lifetime; a context
        # manager would close it between samples.
        self.handle = open(self.fullpath)  # noqa: SIM115

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


class PsiScreen(Screen):
    """Behavior every psistat screen shares: quit ends the run loop."""

    def quit_ACTION(self):
        """End the run loop; curses is stopped by ``main()``."""
        self.app.running = False


class ReportScreen(PsiScreen):
    """The home screen: the stats band and the newest threshold events."""

    name = 'REPORT'

    def help_screen_ACTION(self):
        """``?`` opens the help page; ESC is the only way back."""
        self.app.stack.push(self.app.help, self.pick_pos)

    def draw_screen(self):
        self.set_pick_mode(False)
        app = self.app
        self.add_fancy_header(app.title_line(), mode='Underline', line_attr=cs.A_DIM)
        self.add_header(STAT_HEADER)
        for tag in ('cpu', 'io', 'memory'):
            self.add_header(self.stat_line(f'{tag}.full') + '     '
                            + self.stat_line(f'{tag}.some'))
        self.draw_events()

    def stat_line(self, key):
        """One six-column stats run and its group tag, for *key*."""
        cells = ''.join((' ' + 'n/a'.rjust(6)) if pct is None else f' {pct:6.2f}'
                        for pct in self.app.pcts.get(key, (None, None, None, None, None)))
        return cells + f'  {key.split(".")[0]:<6}'

    def draw_events(self):
        """Append the newest events: as many as fit in brief mode, else 200."""
        app = self.app
        # calc() is what refreshes body_base from the rows just appended.
        self.win.calc()
        brief = app.opts.brief == 'on'
        limit = max(self.win.rows - self.win.body_base, 0) if brief else 200
        for idx, (mono_ns, descr) in enumerate(app.events):
            if idx >= limit:
                break
            ago = ago_str((time.monotonic_ns() - mono_ns)/BILLION).strip()
            self.add_body(f'{idx:03d} {ago:>6s}: {descr}')

    def dump_event_log_ACTION(self):
        """``d``: print the whole log on the terminal, then come back."""
        self.app.dump_event_log()


class HelpScreen(PsiScreen, BasicHelpScreen):
    """The built-in help page, scoped to the report it was pushed from."""

    name = 'HELP'

    def extra_help_paragraphs(self):
        return (
            'Events are collected once per second in the background.',
            'The report lists the newest ones under the stats.',
            'The log keeps the last 1000.',
        )


class PsiStat:
    """Class to display PSI information including
    running averages and exception events"""
    singleton = None
    window_backend = None
    window_singleton = True

    def __init__(self, threshold=5, brief=False, itvl=10):
        assert self.singleton is None
        PsiStat.singleton = self
        self.stats = { 'cpu.full': None, 'cpu.some': None,
                       'io.full': None, 'io.some': None,
                       'memory.full': None, 'memory.some': None
                     }
        self.pcts = {}        # {stat key: [1s, 3s, 10s, 60s, 300s]} for the report
        self.monos = []
        self.times = []
        self.psgs = []
        self.events = []
        self.event_floor = {}
        self.last_sample_mono = 0
        self.running = True

        # --- CONSOLE-WINDOW SETUP ---
        # Options live on a plain object; the spinner writes
        # the user's values there and the screens read them, so neither needs a mode flag.
        self.opts = SimpleNamespace(event_interval=itvl, threshold=threshold,
                                    brief='on' if brief else 'off')

        win_opts = ConsoleWindowOpts(head_line=True, ctrl_c_terminates=False,
                                     min_cols_rows=(80, 10))
        self.win = ConsoleWindow(opts=win_opts, backend=self.window_backend,
                                 singleton=self.window_singleton)

        # Construction order: window -> screens -> stack -> spinner -> keys.
        self.report = ReportScreen(self)
        self.help = HelpScreen(self)
        self.stack = ScreenStack.from_screens(self.win, self.opts,
                                              [self.report, self.help])
        self.spin = self.build_spinner()
        self.win.set_handled_keys(self.spin)

        for tag in 'cpu', 'io', 'memory':
            self.psgs.append(PressureGroup(tag, self.stats))

    def build_spinner(self):
        """Register the keys; ``quit`` and the ``?`` toggle are actions."""
        spin = OptionSpinner(
            stack=self.stack,
            nav_keys=self.win.opts.nav_keys,
            quit_keys=(ord('q'), ord('Q'), 0x3),
            escape_keys=[27],   # ESC is the only way back
        )
        spin.add_key('event_interval', 'i - event interval (secs)',
                     vals=[10, 3, 1, 300, 60])
        spin.add_key('threshold', 't - set event threshold percent [1,99]',
                     prompt='Enter event threshold percent in range [1,99]',
                     check_ans=check_threshold)
        spin.add_key('brief', 'b - only load events that fit on screen',
                     vals=['off', 'on'])
        spin.add_key('dump_event_log', 'd - dump event log to the terminal',
                     keys=[ord('d')], genre='action')
        spin.add_key('help_screen', '? - show help',
                     keys=[ord('?')], genre='action')
        return spin

    def threshold_pct(self):
        """The threshold as an int: a prompt stores its validated text."""
        return int(self.opts.threshold)

    def title_line(self):
        """The report's title header, with each control key marked."""
        hhmmss = datetime.fromtimestamp(time.time()).strftime("%H:%M:%S")
        line = HeaderLine()
        line.label('PSIs').text(f' {hhmmss} | ')
        line.bracket_key('t').text(f'hresh={self.threshold_pct()}%  ')
        line.bracket_key('i').text(f'tvl={self.opts.event_interval}s  ')
        line.bracket_key('b').text(f'rief={self.opts.brief}  ')
        line.bracket_key('d').text('ump  ')
        line.bracket_key('?').text(':help  ')
        line.bracket_key('q').text('uit')
        return line

    def dump_event_log(self):
        """Drop out of the window, dump the event log, return on ENTER."""
        self.win.suspend_curses()
        try:
            os.system('clear')
            for _mono, descr in reversed(self.events):
                print(descr)
            try:
                input('\n\n===== Press ENTER to return to psistat ====> ')
            except EOFError:
                pass
        finally:
            self.win.resume_curses()

    def count_valid_samples(self):
        """ Valid samples are no worse that 1.25s later than the one before
         and no more than SAMPLES
        """
        # return SAMPLES-1
        count = 1
        del self.monos[SAMPLES:]
        for loop in range(len(self.monos) - 1):
            delta_ns = self.monos[loop] - self.monos[loop+1]
            if  delta_ns > 1000000000 * 1.25:
                break
            count += 1
        return count

    def process_psgs(self):
        """Sample the kernel, then compute this pass's percentages and events."""
        for psg in self.psgs:
            psg.add_sample()

        self.times.insert(0, time.time())
        mono = time.monotonic_ns()
        self.monos.insert(0, mono)
        valid_sample_count = self.count_valid_samples()
        del self.monos[valid_sample_count:]
        del self.times[valid_sample_count:]

        self.pcts = self.compute_pcts(valid_sample_count)

    def compute_pcts(self, valid_sample_count):
        """Return the stat percentages, recording threshold events on the way.

        The event record is built exactly as the report used to build it while drawing:
        a ``full`` and a ``some`` crossing at the same instant share one event,
        and a lone ``some`` is dotted out to keep the columns aligned.
        ``event_floor`` stops one crossing from repeating within the event interval.
        """
        threshold = self.threshold_pct()
        itvl = self.opts.event_interval
        now = time.time()
        pcts = {}
        event = ''
        specifically = ''
        for key, value in self.stats.items():
            micros = value.micros
            del micros[valid_sample_count:]
            avgs = self.stats[key].avgs
            cells = []
            for ii in (1, 3, 10, 60, 300):
                if ii in (1, 3, 10):
                    if len(micros) <= ii:
                        cells.append(None)
                        continue

                    delta_micros = (micros[0] - micros[ii])
                    delta_monos = (self.monos[0] - self.monos[ii])

                    if delta_monos == 0:
                        pct = 0.0
                    else:
                        pct = 100 * 1000 * delta_micros / delta_monos

                else:
                    pct = avgs.get(ii, 0.0)

                cells.append(pct)

                # detect/collect samples that exceed the threshold
                floor_key = f'{key}.{ii}'
                floor = self.event_floor.get(floor_key, 0)
                if ii == itvl and round(pct, 2) >= threshold and now >= floor:
                    if not event:
                        dt_object = datetime.fromtimestamp(now)
                        # Truncate microseconds to milliseconds (.mmm) with [:-3]
                        event += dt_object.strftime("%m-%d %H:%M:%S.%f")[:-3]

                    specifically = f'{pct:7.2f}% {key:<11s}'
                    if '.full' not in event and '.some' in key:
                        event += '  ' + '.' * len(specifically)
                    event += '  ' + specifically
                    self.event_floor[floor_key] = now + itvl
            pcts[key] = cells

            if key.endswith('.some') and event:
                event += f'   >={threshold}% i={itvl}s'
                self.events.insert(0, (time.monotonic_ns(), event))
                event = ''

        del self.events[1000:]
        return pcts

    def loop(self):
        """Do one loop of collecting samples, and then displaying running
        averages and exception events."""
        timeout_secs, min_timout_secs = 1.0, 0.9

        if time.monotonic() - self.last_sample_mono >= min_timout_secs:
            self.process_psgs()
            self.last_sample_mono = time.monotonic()

        screen = self.stack.get_curr_obj()
        screen.clear()
        screen.draw_screen()

        # Render the screen
        self.win.render()
        sleep_secs = timeout_secs - (time.monotonic() - self.last_sample_mono)

        # Wait for input/timeout using ConsoleWindow.prompt()
        keystroke = self.win.prompt(seconds=sleep_secs)

        if keystroke is not None:
            try:
                self.spin.do_key(keystroke, self.win)
            except TerminalTooSmallError as exc:
                # A prompt needs a bigger terminal than the main screen.
                # Keep running and show the requirement on the status
                # row instead of bailing out; the status clears itself.
                self.win.status(str(exc), level='warn', timeout=5)
                return True
            # do_key() only sets flags; the screens' *_ACTION methods run here.
            self.stack.perform_actions(self.spin)

        return self.running


def main():
    """Main execution function, handles CLI arguments."""
    # Answer `--version` before anything touches curses or /proc
    if '--version' in sys.argv[1:]:
        print(f'psistat {__version__}')
        return

    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--brief', action='store_true',
                        help='whether present only as meny events as fit on the screen')
    parser.add_argument('-i', '--event-interval', default=10, type=int, choices=[1,3,10,60,300],
                        help='average interval used for events')
    parser.add_argument('-t', '--threshold-pct', default=5, type=int,
                        help='event threshold percent [1-99,dflt=5]')
    opts = parser.parse_args()

    pct = min(max(opts.threshold_pct, 1), 99)

    try:
        pstall = PsiStat(threshold=pct, brief=opts.brief, itvl=opts.event_interval)
        while pstall.loop():
            pass
    # The top-level guard must report every failure, including one raised before
    # the window exists; narrowing it would hide errors the user needs to see.
    except Exception as exc:  # noqa: BLE001
        # 'window' may not exist yet if the failure happened during PsiStat.__init__.
        window = getattr(PsiStat.singleton, 'win', None) if PsiStat.singleton else None
        if window:
            window.stop_curses()

        print("exception:", str(exc))
        print(traceback.format_exc())
    else:
        pstall.win.stop_curses()
