"""
    A not so simple game of Tic-Tac-Toe.
"""
import atexit
import math
import os
import random
import shutil
import sys
import time
from functools import lru_cache

PALETTE = [196, 202, 208, 214, 220, 226, 190, 154, 118, 82, 46, 48, 51, 45, 39, 33, 27, 21, 57, 93, 129, 165, 201, 199]     # vivid ANSI 256 colors
SYMBOL_POOL = "#@%&*+$~^?!=<>ABCDEFGHJKLMNOPQRSTUVWXYZ"
COLOR_DISTANCES = (220, 190, 160, 130, 100, 70)     # how different the players' colors should be at least, tried from the biggest down
MAX_PLAYERS = 12
MESSAGE_LINES = 6       # how many of the last messages stay on the screen
TIMEOUT = None          # seconds until an unanswered question takes its default, None = no timeout, asked at the start
GAMBLE_MIN = 0.1        # the smallest share of the gamble chance that stays even when blocking costs nothing
RELIABILITY = {True: 0.9, False: 0.6}       # how likely a computer / a human blocks a threat for somebody else
SCORE_EAGERNESS = 0.7   # how much a leader's score takes from the gamble chance, only for threats that wait for the next round
BAR_WIDTH = 20        # cells of the timer bar
try:
    '█░'.encode(sys.stdout.encoding or 'ascii')
    BAR_FULL, BAR_EMPTY = '█', '░'
except UnicodeEncodeError:                          # an old code page without block characters
    BAR_FULL, BAR_EMPTY = '#', '-'
TIMED_OUT = object()    # what timed_input gives back when nobody answered

messages = []
players = []            # list of (name, symbol)
colors = {}             # symbol -> color code
computers = set()       # names of the computer players
scores = {}             # name -> score
draws = 0               # how many rounds ended in a draw
in_game = False         # False during the setup, True as soon as the board is set
banner = []             # the first lines of the screen, always there, made once so the rainbow keeps its colors
board_title = ''        # the line above the board
symbols = []
board_dictionary = {}   # empty as long as there is no board
x, y, z = 1, 0, 3       # x is for spaces in user symbols, y² is board size, z is winning condition
screen_started = False


def thanks():
    say("Very nice! This is what we have:")

def paint(text, color):
    """
        Wraps text in an ANSI 256-color code
    """
    return f"\033[38;5;{color}m{text}\033[0m"

def rainbow(text):
    """
        Every letter in an own random color
    """
    return ''.join(ch if ch == ' ' else paint(ch, random.choice(PALETTE)) for ch in text)

banner[:] = [rainbow(' Welcome to a new version of Tic-Tac-Toe! '),
             "Up to 12 players, human or computer.",
             "Scalable board and winning condition.",
             "Shuffled turns of players in every round."]
board_title = rainbow(" Good luck my friends ! ")

def timer_bar(remaining):
    """
        Draws the timer bar on the row below the input line and puts the cursor back, remaining=None erases it
    """
    if remaining is None:
        bar = ''
    else:
        share = max(0, remaining) / TIMEOUT
        filled = min(BAR_WIDTH, math.ceil(share * BAR_WIDTH))
        color = 46 if share > 0.5 else 226 if share > 0.25 else 196      # green, yellow, red
        bar = paint(BAR_FULL * filled, color) + BAR_EMPTY * (BAR_WIDTH - filled) + " %ds" % math.ceil(max(0, remaining))
    sys.stdout.write('\0337\033[1B\r' + bar + '\033[K\0338')       # save the cursor, one row down, draw, back
    sys.stdout.flush()

def timed_input(prompt):
    """
        Like input(), but gives TIMED_OUT when nothing is typed for TIMEOUT seconds (every key restarts the time)
        Without a terminal, e.g. in a pipe, or without a TIMEOUT it is a plain input()
    """
    if TIMEOUT is None or not sys.stdin.isatty():
        return input(prompt)
    sys.stdout.write(prompt)
    sys.stdout.flush()
    deadline = time.monotonic() + TIMEOUT
    if os.name == 'nt':
        import msvcrt
        typed = ''
        shown = None
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            state = (math.ceil(remaining / TIMEOUT * BAR_WIDTH), math.ceil(remaining))
            if state != shown:                      # only redraw the bar when it changes
                timer_bar(remaining)
                shown = state
            if not msvcrt.kbhit():
                time.sleep(0.02)
                continue
            key = msvcrt.getwch()
            deadline = time.monotonic() + TIMEOUT
            if key in '\r\n':
                timer_bar(None)
                sys.stdout.write('\n')
                sys.stdout.flush()
                return typed
            if key == '\x03':
                raise KeyboardInterrupt
            if key in '\x00\xe0':                   # arrow and function keys come as two characters
                msvcrt.getwch()
            elif key == '\x08':
                if typed:
                    typed = typed[:-1]
                    sys.stdout.write('\b \b')
            elif key.isprintable():
                typed += key
                sys.stdout.write(key)
            sys.stdout.flush()
    else:
        import select
        while deadline - time.monotonic() > 0:
            timer_bar(deadline - time.monotonic())
            if select.select([sys.stdin], [], [], 0.1)[0]:
                timer_bar(None)
                return sys.stdin.readline().rstrip('\n')
    timer_bar(None)
    sys.stdout.write('\n')
    return TIMED_OUT

def ask(question, default=''):
    """
        Draws the screen and asks the question, a timeout gives the default
    """
    render()
    sys.stdout.write('\033[?25h')                  # the cursor is visible while typing
    answer = timed_input(question)
    if answer is TIMED_OUT:
        say("No answer in %d seconds, the default is taken." % TIMEOUT)
        return default
    return answer

def ask_int(question, default, minimum):
    """
        Asks until the answer is an integer >= minimum, <Enter> gives the default
    """
    while True:
        answer = ask(question).strip()
        if answer == '':
            return default
        if answer.isdigit() and int(answer) >= minimum:
            return int(answer)
        say("Please type an integer of at least %d or hit <Enter>." % minimum)

def min_side(n, z, step=None, margin=None):
    """
        Minimum side of the board for n players and the winning condition z:
        z + (n - 2) * step, but at least z + margin
        Defaults: step = z - 2, margin = 1 for z > 3 (0 for z = 3, which keeps the classic 3x3)
        None means the default
    """
    step = z - 2 if step is None else step
    margin = (1 if z > 3 else 0) if margin is None else margin
    return max(z + (n - 2) * step, z + margin)

def formula_setup():
    """
        Asks if the minimum board formula should be changed. <Enter> takes the default without further asking
        Returns the rules: players n, winning condition z, step and margin (None = default), custom flag
    """
    rules = {'n': 2, 'z': 3, 'step': None, 'margin': None, 'custom': False}
    say("The minimum side of the board is: z + (n - 2) * step, at least z + margin")
    say("n = players, z = winning condition, step = extra rows per player beyond 2 (default z - 2), margin = extra rows over z (default 1 for z > 3, else 0)")
    if ask("Hit <Enter> for the default (2 players, z = 3) or any other key to set the variables: ") == '':
        return rules
    rules['custom'] = True
    rules['n'] = ask_int("n, number of players (2-%d), <Enter> for 2: " % MAX_PLAYERS, 2, 2)
    rules['n'] = min(rules['n'], MAX_PLAYERS)
    rules['z'] = ask_int("z, winning condition (3 or more), <Enter> for 3: ", 3, 3)
    default_step = rules['z'] - 2
    rules['step'] = ask_int("step, extra rows per additional player, <Enter> for %d: " % default_step, default_step, 0)
    default_margin = 1 if rules['z'] > 3 else 0
    rules['margin'] = ask_int("margin, extra rows over z, <Enter> for %d: " % default_margin, default_margin, 0)
    say("Minimum side: %d" % min_side(rules['n'], rules['z'], rules['step'], rules['margin']))
    return rules

def color_distance(code1, code2):
    """
        How different two ANSI 256 colors (from the 6x6x6 color cube) look, "redmean" weighted RGB distance
        0 = the same, around 100 = hard to tell apart, 200 and more = clearly different
    """
    levels = (0, 95, 135, 175, 215, 255)
    r1, g1, b1 = (levels[(code1 - 16) // 36], levels[(code1 - 16) // 6 % 6], levels[(code1 - 16) % 6])
    r2, g2, b2 = (levels[(code2 - 16) // 36], levels[(code2 - 16) // 6 % 6], levels[(code2 - 16) % 6])
    red_mean = (r1 + r2) / 2
    return ((2 + red_mean / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - red_mean) / 256) * (b1 - b2) ** 2) ** 0.5

def pick_colors(n):
    """
        n random colors from the PALETTE that are not too similar
        It asks for the biggest distance from COLOR_DISTANCES that n colors can keep, the more players the smaller it gets
    """
    n = min(n, len(PALETTE))
    for limit in COLOR_DISTANCES:
        for attempt in range(20):
            chosen = []
            for code in random.sample(PALETTE, len(PALETTE)):
                if all(color_distance(code, other) >= limit for other in chosen):
                    chosen.append(code)
                    if len(chosen) == n:
                        return chosen
    return random.sample(PALETTE, n)

def users_input(n):
    """
        Takes user input for the names and symbols of n players, strips the symbol to 1 character
        <Enter> on the symbol question gives a random free symbol, every player gets an own random color
        <Enter> on the name question makes a computer player, it gets a random symbol without asking
        Returns the players as list of (name, symbol), the colors as dictionary symbol -> color code and the names of the computer players
    """
    say("Let us start with the user questionary!")
    colors = {}
    players = []
    computers = set()
    free_colors = pick_colors(n)
    taken = set()
    for i in range(n):
        name = ask("Player %d, what's your name? Hit <Enter> for a computer player " % (i + 1)).strip()
        is_computer = name == ''
        if is_computer:
            name = 'Computer %d' % (i + 1)
            computers.add(name)
        elif name in [known for known, _ in players]:
            name = "%s (%d)" % (name, i + 1)
            say("The name is taken, you are", name)
        while True:
            input_symbol = '' if is_computer else ask("%s, which symbol do you want to use? Hit <Enter> for a random one " % name).strip()
            if input_symbol == '':
                input_symbol = random.choice([c for c in SYMBOL_POOL if c not in taken])
                break
            if input_symbol[0] in taken:
                say("This symbol is already used, please pick another one.")
            else:
                break
        taken.add(input_symbol[0])
        symbol = ' ' + input_symbol[0] + ' '     # mind the pesky spaces: they are used in the board
        colors[symbol] = free_colors[i] if i < len(free_colors) else random.choice(PALETTE)
        players.append((name, symbol))
        say("- ", name, "using the symbol", paint(symbol, colors[symbol]), "(computer)" if is_computer else "")
    thanks()

    return players, colors, computers

def free_fields():
    """
        The keys of all fields without a symbol
    """
    return [k for k, value in board_dictionary.items() if value not in symbols]

def open_windows(symbol):
    """
        The lines (see window_keys) that hold no other symbol than the given one, so the player can still win with them
        Returns tuples of (keys, own symbols in the line, keys of the empty fields)
    """
    result = []
    for keys in window_keys(y, z):
        cells = [board_dictionary[k] for k in keys]
        if all(c == symbol or c not in symbols for c in cells):
            result.append((keys, sum(c == symbol for c in cells), [k for k, c in zip(keys, cells) if c not in symbols]))
    return result

def win_cells(symbol):
    """
        The fields that complete a line for the symbol right now
    """
    return {empty[0] for _, _, empty in open_windows(symbol) if len(empty) == 1}

def cell_scores(symbol):
    """
        Rates every free field for the symbol:
        every open line through the field counts 3 ** own symbols in it, so a field in many and well filled lines is strategic
        a field that brings two or more lines one step before the win (a fork) gets a bonus
        the open lines of the opponents count half, so a field that spoils them is a little better
    """
    scores = dict.fromkeys(free_fields(), 0.0)
    forks = dict.fromkeys(scores, 0)
    for _, own, empty in open_windows(symbol):
        for k in empty:
            scores[k] += 3 ** own
            if own == z - 2:
                forks[k] += 1
    for _, other_symbol in players:
        if other_symbol != symbol:
            for _, own, empty in open_windows(other_symbol):
                for k in empty:
                    scores[k] += 0.5 * 3 ** own
    for k, count in forks.items():
        if count >= 2:
            scores[k] += 50 * (count - 1)
    return scores

def best_cell(cells, symbol):
    """
        The best rated of the cells, a random one of the equally good
    """
    scores = cell_scores(symbol)
    top = max(scores[c] for c in cells)
    return random.choice([c for c in cells if scores[c] == top])

def score_excess(name):
    """
        How far the player is above the average score, from 0 (average or below) to 1 (has all the points)
    """
    total = sum(scores.values())
    if total == 0 or len(scores) < 2:
        return 0.0
    return max(0.0, scores[name] * len(scores) / total - 1) / (len(scores) - 1)

def gamble_chance(name, symbol, threats, later):
    """
        How likely the computer leaves the threats (field -> names of the players who win there) to the players behind it
        0 means it must block. Otherwise: p_gamble = p_cover * (GAMBLE_MIN + (1 - GAMBLE_MIN) * gain) * eagerness
        - blockers: the players who move after this one and before the first threatener of the field,
          a threatener who already moved comes only in the next round, so all players in later are in front of it
          if nobody is left, or fewer blockers than threatened fields, it must block
        - p_cover: all fields get blocked by somebody, a blocker is reliable as RELIABILITY says (computer or human)
        - gain: how much better the best field is than the best block, so a block that is the best move anyway is no gamble
        - eagerness: only for a field whose threateners all wait for the next round (random order then): the higher
          the score of the leading threatener, the more the others want to block it instead of gambling
          for threateners of the current round the scores do not count
    """
    chance_cover = 1.0
    eagerness = 1.0
    all_blockers = set()
    for cell, who in threats.items():
        current = [later.index(w) for w in who if w in later]
        blockers = later[:min(current)] if current else later
        if not blockers:
            return 0.0
        all_blockers.update(blockers)
        chance_cover *= 1 - math.prod(1 - RELIABILITY[b in computers] for b in blockers)
        if not current:
            eagerness = min(eagerness, 1 - SCORE_EAGERNESS * max(score_excess(w) for w in who))
    if len(all_blockers) < len(threats):
        return 0.0
    rating = cell_scores(symbol)
    best = max(rating.values())
    gain = (best - max(rating[c] for c in threats)) / best if best > 0 else 0.0
    return chance_cover * (GAMBLE_MIN + (1 - GAMBLE_MIN) * gain) * eagerness

def computer_pick(name, symbol, later=()):
    """
        A computer player, waits for a second and then
        1) completes a line of its own if it can
        2) blocks the opponents that could win with their next symbol, or gambles on the players behind it, see gamble_chance
           (later = names still to move after this player in this round)
        3) and 4) takes the best rated field, see cell_scores
    """
    say(paint(name, colors[symbol]), "is thinking ...")
    render()
    time.sleep(1)
    own_wins = win_cells(symbol)
    if own_wins:
        return random.choice(sorted(own_wins))
    threats = {}                                    # field -> names of the players who win there
    for other, other_symbol in players:
        if other != name:
            for cell in win_cells(other_symbol):
                threats.setdefault(cell, set()).add(other)
    if threats and random.random() >= gamble_chance(name, symbol, threats, list(later)):
        return best_cell(list(threats), symbol)
    return best_cell(free_fields(), symbol)


def say(*parts):
    """
        Collects a message for the screen, only the last MESSAGE_LINES are kept
    """
    messages.append(' '.join(str(part) for part in parts))
    del messages[:-MESSAGE_LINES]

def enable_ansi():
    """
        Switches the Windows console to ANSI codes and brings the cursor back at the end
    """
    if os.name == 'nt':
        os.system('')
    atexit.register(lambda: sys.stdout.write('\033[?25h'))

def score_lines():
    """
        The score of every player in the player's color
    """
    return ["- %s %s score: %d%s" % (paint(name, colors[symbol]), paint(symbol, colors[symbol]), scores[name], " (computer)" if name in computers else "")
            for name, symbol in players]

def render():
    """
        Draws the whole screen in one write: scores, board and the last messages, always at the same place
        The cursor goes home and every line overwrites the old one, nothing is cleared in between, so nothing flickers
        The input line follows below the last message
    """
    global screen_started
    lines = banner + ['']
    if in_game:
        lines += ["Board: %d x %d = %d fields, winning condition: %d in a row, %d players" % (y, y, y ** 2, z, len(players))]
        lines += score_lines() + ["- draws: %d" % draws]
    else:
        lines += ["Setup: first the board formula, then the names and symbols of the players (<Enter> on a name makes a computer player),",
                  "then the board size and the winning condition."]
    if board_dictionary:
        lines += [''] + board_lines()
    lines += [''] + messages + [''] * (MESSAGE_LINES - len(messages))
    frame = '\033[?25l\033[H' + ''.join(line + '\033[K\n' for line in lines) + '\033[J'
    if not screen_started or len(lines) + 3 > shutil.get_terminal_size().lines:
        frame = '\033[2J' + frame                 # the first time, and when the screen is too small to hold it
        screen_started = True
    sys.stdout.write(frame)
    sys.stdout.flush()

def board_square(rules):
    """
        Takes any board size, finds the next perfect square, also adds spaces tu users symbols for the correct work of the board
        The side is raised to the minimum of the multiplayer formula (see min_side)
    """
    say("We need to create a board. It will be a square (for now) but the size can be your choice.")
    say("Think big and don't worry if you do not remember all perfect squares.")          # If you think > 1000 the board will use a variable space slicer
    first_floor = min_side(rules['n'], rules['z'], rules['step'], rules['margin'])      # the minimum for the chosen players and z
    default_size = max(9, first_floor ** 2)
    if first_floor > 3:
        say("For %d players and a winning condition of %d the board needs at least %d x %d = %d fields." % (rules['n'], rules['z'], first_floor, first_floor, first_floor ** 2))
    input_size = ask_int('Please type any integer or hit <Enter> to use a standard of %d: ' % default_size, default_size, 1)
    if input_size < 7:
        input_size = 9
    x = 1               # for the spaces added to user symbols on large boards
    y = 1               # one side of board, asking for it would be too easy ;)
    z = rules['z']      # winning condition
    while abs(input_size - (y ** 2)) > abs(input_size - ((y + 1) ** 2)):      # Cheat mode on: it gives the closest perfect square
        y += 1
    if y > 3 and not rules['custom']:           # a customized formula has asked for z already
        say("\033[92m Amazing! You are setting up a big challenge. Now it's time to think about the winning condition. \033[0m")
        z = ask_int('Please type any integer or hit <Enter> to use a standard of 3: ', 3, 2)
        if z > y:
            z = y             # in the ultimate tic-tac-toe the winning condition is 3 for the 3x3 board and 3 (3x3 boards) for the big 9x9 board.
            say("\033[0;31m You are thinking around the corner? \033[0m", "With the board size of ", y**2, "= ", y,"² the winning condition is restricted to ", y)
    floor = min_side(rules['n'], z, rules['step'], rules['margin'])
    if y < floor:
        say("\033[0;31m Too small for %d players and a winning condition of %d. \033[0m" % (rules['n'], z), "The side is raised from", y, "to", floor)
        y = floor
    if y > 10:
        x += 1
    thanks()
    say("The board size will be: ", y ** 2)
    say("The winning condition is: ", z)
    say("We are all set to start the game.")
    nothing = ask(rainbow(" Hit any key to start! "))
    return x, y, z

def board_generator():
    """
        Generates the board as a dictionary with a key list from 1 to y^2 and fills values to serve as coordinates
    """
    board_size = y ** 2
    board_fields = list(range(1, board_size + 1))
    board_dictionary = dict((el, str(el)) for el in board_fields)     # other option without coordinates: dict((el, ' ') for el in board_fields)
    return board_dictionary

def board_lines():
    """
        The board with values as a list of lines

        *** Cheat mode on ***
        How it works:
        row * y + col + 1 calculates the dictionary key for each cell (1-indexed)
        range(y) gives you 0, 1, 2 for both rows and columns
        List comprehension builds each row, then " | ".join() formats it
        *** Cheat mode off ***

    """
    width = max(3, len(str(y ** 2)))                                     # a cell is as wide as the biggest field number, at least 3
    separator = ('+' + '-' * (width + 2)) * y + '+'
    lines = [board_title, separator]
    symbol_filler = ' ' * x                                              # can use instead of ' ' for really large boards
    for row in range(y):
        row_values = [board_dictionary[row * y + col + 1] for col in range(y)]
        centered_values = [val.center(width) for val in row_values]      # the numbers have no leading zeros, the cells keep their width
        colored_values = [paint(text, colors[val]) if val in colors else text for val, text in zip(row_values, centered_values)]   # every player has an own color
        lines.append("| " + " | ".join(colored_values) + " |")
        lines.append(separator)
    return lines

def ask_field(user):
    """
        Requires user input for a field, a timeout takes a random free field
    """
    while True:
        answer = ask("%s, Your turn! Type a field number! " % user, default=None)
        if answer is None:
            return random.choice(free_fields())
        answer = answer.strip()
        if not answer.isdigit() or not 1 <= int(answer) <= len(board_dictionary):
            say("Please type a number from 1 to %d." % len(board_dictionary))
        elif board_dictionary[int(answer)] in symbols:
            say("Field %d is used, please pick a free one." % int(answer))
        else:
            return int(answer)

def field_filler(field, symbol):
    """
        Inserts into the dictionary the symbol from last input
    """
    say("Excellent, '%s' put on field:" % paint(symbol, colors[symbol]), field)
    board_dictionary[field] = symbol

def check_winner(check_name, check_symbol, board=None):
    """
        Checking z same consecutive symbols in rows, columns and diagonals

        *** Cheat mode on ***
        Check all diagonals (both directions)
        For each possible diagonal offset, generate the sequence of keys
        and check for z consecutive symbols
        *** Cheat mode off ***

    """

    board = board_dictionary if board is None else board     # another board can be passed
    current_symbol = check_symbol
    be_winner = ''

    # Check rows
    for row_start in range(1, len(board) + 1, y):
        # Keys in the current row
        row_keys = list(range(row_start, row_start + y))
        # Check every window of length z in this row
        for i in range(len(row_keys) - z + 1):
            # Get the keys for the current window
            combo_keys = row_keys[i:i + z]
            # Concatenate the corresponding values
            compare_str = ''.join(board[k] for k in combo_keys)
            # Check for a match
            if compare_str == current_symbol * z:
                be_winner = check_name

    # Check columns
    for col_start in range(1, y + 1):
        col_keys = [col_start + offset * y for offset in range(y)]
        # Slide a window of length z down the column
        for i in range(len(col_keys) - z + 1):
            combo_keys = col_keys[i:i + z]
            compare_str = ''.join(board[k] for k in combo_keys)
            if compare_str == current_symbol * z:
                be_winner = check_name

    # Main diagonals (top-left to bottom-right)
    for start_row in range(y):
        diag_keys = []
        row, col = start_row, 0
        while row < y and col < y:
            key = row * y + col + 1
            diag_keys.append(key)
            row += 1
            col += 1
        # Check this diagonal for winning sequences
        for i in range(len(diag_keys) - z + 1):
            combo_keys = diag_keys[i:i + z]
            compare_str = ''.join(board[k] for k in combo_keys)
            if compare_str == current_symbol * z:
                be_winner = check_name

    for start_col in range(1, y):
        diag_keys = []
        row, col = 0, start_col
        while row < y and col < y:
            key = row * y + col + 1
            diag_keys.append(key)
            row += 1
            col += 1
        # Check this diagonal for winning sequences
        for i in range(len(diag_keys) - z + 1):
            combo_keys = diag_keys[i:i + z]
            compare_str = ''.join(board[k] for k in combo_keys)
            if compare_str == current_symbol * z:
                be_winner = check_name

    # Anti-diagonals (top-right to bottom-left)
    for start_row in range(y):
        diag_keys = []
        row, col = start_row, y - 1
        while row < y and col >= 0:
            key = row * y + col + 1
            diag_keys.append(key)
            row += 1
            col -= 1
        # Check this diagonal for winning sequences
        for i in range(len(diag_keys) - z + 1):
            combo_keys = diag_keys[i:i + z]
            compare_str = ''.join(board[k] for k in combo_keys)
            if compare_str == current_symbol * z:
                be_winner = check_name

    for start_col in range(y - 1):
        diag_keys = []
        row, col = 0, start_col
        while row < y and col >= 0:
            key = row * y + col + 1
            diag_keys.append(key)
            row += 1
            col -= 1
        # Check this diagonal for winning sequences
        for i in range(len(diag_keys) - z + 1):
            combo_keys = diag_keys[i:i + z]
            compare_str = ''.join(board[k] for k in combo_keys)
            if compare_str == current_symbol * z:
                be_winner = check_name
    return be_winner

@lru_cache(maxsize=None)
def window_keys(side, length):
    """
        All lines of `length` consecutive fields (rows, columns, both diagonals) as tuples of dictionary keys
    """
    windows = []
    for row in range(side):
        for col in range(side):
            for d_row, d_col in ((0, 1), (1, 0), (1, 1), (1, -1)):
                end_row, end_col = row + (length - 1) * d_row, col + (length - 1) * d_col
                if 0 <= end_row < side and 0 <= end_col < side:
                    windows.append(tuple((row + i * d_row) * side + col + i * d_col + 1 for i in range(length)))
    return windows

def draw_checker(players, pending=None):
    """
        Checks if winning is impossible on the current board

        players: list of (name, symbol) tuples, any number of players
        pending: names still to move in the current round (default: all), the order of the next rounds is random
        A player can only win with a line that holds no other symbol and whose empty fields
        he can still fill: he moves once per round, so with e empty fields he gets at most one move
        in the current round (if pending) and one in each of the following rounds (n moves each).
        That is an upper bound, so a 'draw' is always a real one.
        If nobody has such a line it returns 'draw', else ''
    """
    symbols = [symbol for _, symbol in players]
    empty = sum(1 for value in board_dictionary.values() if value not in symbols)
    n = len(players)
    pending = [name for name, _ in players] if pending is None else pending
    after_round = max(0, empty - len(pending))
    for name, symbol in players:
        moves = (1 if name in pending and empty > 0 else 0) + (after_round + n - 1) // n        # the fields this player still gets to fill
        for keys in window_keys(y, z):
            cells = [board_dictionary[k] for k in keys]
            if all(c == symbol or c not in symbols for c in cells) and sum(c not in symbols for c in cells) <= moves:
                return ''                              # this player can still win
    return 'draw'

if __name__ == "__main__":
    enable_ansi()
    running = ''
    board_set = False                                      # the board is asked for once, a revanche keeps it
    TIMEOUT = ask_int("Type a number of seconds after which a choice is made automatically if you give no input, or hit <Enter> for no timeout: ", None, 1)
    say("The automatic choice comes after %d seconds." % TIMEOUT if TIMEOUT else "There is no timeout.")
    rules = formula_setup()
    players, colors, computers = users_input(rules['n'])     # players: list of (name, symbol), colors: symbol -> color code
    symbols = [symbol for _, symbol in players]
    scores = {name: 0 for name, _ in players}
    while running == '':
        # Start a new round of Tic-tac-toe
        winner = ''
        board_dictionary = {}                                  # the old board leaves the screen
        messages.clear()
        say(rainbow(' Let us start a new round of Tic-Tac-Toe! '))
        if not board_set:
            x, y, z = board_square(rules)   # x is for spaces in user symbols, y² is board size, z is winning condition
            board_set = True
            in_game = True
        board_dictionary = board_generator()
        messages.clear()
        # the input beginns here
        while winner == '':
            order = random.sample(players, len(players))        # every round of turns has a new random order
            for index, (name, symbol) in enumerate(order):
                later = [next_name for next_name, _ in order[index + 1:]]
                pick = computer_pick(name, symbol, later) if name in computers else ask_field(name)
                field_filler(pick, symbol)
                winner = check_winner(name, symbol)
                if winner == '':
                    winner = draw_checker(players, later)         # 'draw' ends the round, too
                if winner != '':
                    break
        messages.clear()                                       # the last board stays on the screen above the result
        if winner != 'draw':
            scores[winner] += 1                                # the scores are on the screen, too
            say(paint(winner + ' Is the winner!', colors[dict(players)[winner]]))
            losers = [name for name, _ in players if name != winner]
            say(", ".join(losers) + ",", rainbow("how about a revanche?"))
        else:
            draws += 1
            say(rainbow("It's a draw!"), "Shall we start a new round?")
        running = ask("Hit <Enter> for yes or any other key for no: ")
    say("The game is over.")
    render()
