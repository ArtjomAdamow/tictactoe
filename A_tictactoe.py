"""
    A not so simple game of Tic-Tac-Toe, the terminal client: the rules and the computer player are in game.py.
"""
import atexit
import math
import os
import random
import shutil
import sys
import time

import calibrate
from game import Game, MAX_PLAYERS, SYMBOL_POOL, min_side

PALETTE = [196, 202, 208, 214, 220, 226, 190, 154, 118, 82, 46, 48, 51, 45, 39, 33, 27, 21, 57, 93, 129, 165, 201, 199]     # vivid ANSI 256 colors
COLOR_DISTANCES = (220, 190, 160, 130, 100, 70)     # how different the players' colors should be at least, tried from the biggest down
MESSAGE_LINES = 6       # how many of the last messages stay on the screen
TIMEOUT = None          # seconds until an unanswered question takes its default, None = no timeout, asked at the start
BAR_WIDTH = 20        # cells of the timer bar
try:
    '█░'.encode(sys.stdout.encoding or 'ascii')
    BAR_FULL, BAR_EMPTY = '█', '░'
except UnicodeEncodeError:                          # an old code page without block characters
    BAR_FULL, BAR_EMPTY = '#', '-'
TIMED_OUT = object()    # what timed_input gives back when nobody answered

messages = []
colors = {}             # symbol -> color code
game = None             # the Game, made when the setup is done
banner = []             # the first lines of the screen, always there, made once so the rainbow keeps its colors
board_title = ''        # the line above the board
x = 1                   # spaces in user symbols
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

def cancel_pressed():
    """
        True if the user hit <c> (on other systems than Windows <c> and <Enter>), without waiting
    """
    if not sys.stdin.isatty():
        return False
    if os.name == 'nt':
        import msvcrt
        pressed = ''
        while msvcrt.kbhit():
            pressed += msvcrt.getwch()
        return 'c' in pressed.lower()
    import select
    return bool(select.select([sys.stdin], [], [], 0)[0]) and sys.stdin.readline().strip().lower().startswith('c')

def simulation_bar(done, total, elapsed):
    """
        The progress function of calibrate.recommend: draws the bar with the estimated time left, False when the user cancels
        The time left is an upper bound, the simulation stops at the first side that is good enough
    """
    if cancel_pressed():
        return False
    share = done / total if total else 1
    left = elapsed / done * (total - done) if done else None
    bar = BAR_FULL * round(share * BAR_WIDTH) + BAR_EMPTY * (BAR_WIDTH - round(share * BAR_WIDTH))
    sys.stdout.write('\r' + bar + " %d%%  " % (share * 100) + ("at most %ds left" % math.ceil(left) if left is not None else "estimating ...") + "  (<c> to cancel)\033[K")
    sys.stdout.flush()
    return True

def simulate_side(rules):
    """
        The optional simulation, see calibrate.recommend: returns the recommended side, None if the user cancelled
    """
    n, z = rules['n'], rules['z']
    say("Simulating random games for %d players and a winning condition of %d ..." % (n, z))
    render()
    try:
        result = calibrate.recommend(n, z, simulation_bar)
    except KeyboardInterrupt:
        result = None
    sys.stdout.write('\r\033[K')
    if result is None:
        say("Simulation cancelled, the formula is used.")
        return None
    side, stored = result
    if stored:
        say("This setup was already simulated before, thanks for contributing! I use stored data - you don't need to wait.")
    say("Recommended minimum side: %d (the formula says %d)" % (side, min_side(n, z, rules['step'], rules['margin'])))
    return side

def floor_side(rules, z):
    """
        The minimum side: the simulated one if there is one for this z, else the formula
    """
    if rules.get('side') and z == rules['z']:
        return rules['side']
    return min_side(rules['n'], z, rules['step'], rules['margin'])

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
    return ["- %s %s score: %d%s" % (paint(name, colors[symbol]), paint(symbol, colors[symbol]), game.scores[name], " (computer)" if name in game.computers else "")
            for name, symbol in game.players]

def render():
    """
        Draws the whole screen in one write: scores, board and the last messages, always at the same place
        The cursor goes home and every line overwrites the old one, nothing is cleared in between, so nothing flickers
        The input line follows below the last message
    """
    global screen_started
    lines = banner + ['']
    if game:
        lines += ["Board: %d x %d = %d fields, winning condition: %d in a row, %d players" % (game.side, game.side, game.side ** 2, game.z, len(game.players))]
        lines += score_lines() + ["- draws: %d" % game.draws]
    else:
        lines += ["Setup: first the board formula, then the names and symbols of the players (<Enter> on a name makes a computer player),",
                  "then the board size and the winning condition."]
    if game and game.board:
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
    first_floor = floor_side(rules, rules['z'])      # the minimum for the chosen players and z
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
    floor = floor_side(rules, z)
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

def board_lines():
    """
        The board with values as a list of lines

        *** Cheat mode on ***
        How it works:
        row * side + col + 1 calculates the dictionary key for each cell (1-indexed)
        range(side) gives you 0, 1, 2 for both rows and columns
        List comprehension builds each row, then " | ".join() formats it
        *** Cheat mode off ***

    """
    side = game.side
    width = max(3, len(str(side ** 2)))                                  # a cell is as wide as the biggest field number, at least 3
    separator = ('+' + '-' * (width + 2)) * side + '+'
    lines = [board_title, separator]
    symbol_filler = ' ' * x                                              # can use instead of ' ' for really large boards
    for row in range(side):
        row_values = [game.board[row * side + col + 1] for col in range(side)]
        centered_values = [val.center(width) for val in row_values]      # the numbers have no leading zeros, the cells keep their width
        colored_values = [paint(text, colors[val]) if val in colors else text for val, text in zip(row_values, centered_values)]   # every player has an own color
        lines.append("| " + " | ".join(colored_values) + " |")
        lines.append(separator)
    return lines

def show_game_messages():
    """
        Moves the messages of the game to the screen, the symbols in the player's color
    """
    for text in game.messages:
        for _, symbol in game.players:
            text = text.replace(symbol, paint(symbol, colors[symbol]))
        say(text)
    game.messages.clear()

def computer_turn(name, later):
    """
        The computer thinks for a second and gives the field it takes
    """
    say(paint(name, colors[game.symbol_of(name)]), "is thinking ...")
    render()
    time.sleep(1)
    return game.computer_pick(name, later)

def ask_field(user):
    """
        Requires user input for a field, a timeout takes a random free field
    """
    while True:
        answer = ask("%s, Your turn! Type a field number! " % user, default=None)
        if answer is None:
            return random.choice(game.free_fields())
        answer = answer.strip()
        if not answer.isdigit() or not 1 <= int(answer) <= len(game.board):
            say("Please type a number from 1 to %d." % len(game.board))
        elif game.board[int(answer)] in game.symbols:
            say("Field %d is used, please pick a free one." % int(answer))
        else:
            return int(answer)

if __name__ == "__main__":
    enable_ansi()
    running = ''
    TIMEOUT = ask_int("Type a number of seconds after which a choice is made automatically if you give no input, or hit <Enter> for no timeout: ", None, 1)
    say("The automatic choice comes after %d seconds." % TIMEOUT if TIMEOUT else "There is no timeout.")
    say("Optional: random games can test the minimum board size for your setup before the game starts.")
    say("Warning: large setups (many players, long winning lines) need a longer runtime, up to many minutes. You can cancel and the formula is used.")
    simulate = ask("Hit <Enter> for no simulation or any other key to simulate: ") != ''
    rules = formula_setup()
    if simulate:
        rules['side'] = simulate_side(rules)
    players, colors, computers = users_input(rules['n'])     # players: list of (name, symbol), colors: symbol -> color code
    while running == '':
        # Start a new round of Tic-tac-toe
        winner = ''
        messages.clear()
        say(rainbow(' Let us start a new round of Tic-Tac-Toe! '))
        if game is None:                                   # the board is asked for once, a revanche keeps it
            x, side, z = board_square(rules)   # x is for spaces in user symbols, side² is board size, z is winning condition
            game = Game(players, computers, side, z)
        else:
            game.new_round()
        messages.clear()
        game.messages.clear()
        # the input beginns here
        while winner == '':
            order = random.sample(players, len(players))        # every round of turns has a new random order
            for index, (name, symbol) in enumerate(order):
                later = [next_name for next_name, _ in order[index + 1:]]
                pick = computer_turn(name, later) if name in game.computers else ask_field(name)
                winner = game.place(name, pick, later)          # 'draw' ends the round, too
                show_game_messages()
                if winner != '':
                    break
        messages.clear()                                       # the last board stays on the screen above the result
        if winner != 'draw':
            say(paint(winner + ' Is the winner!', colors[dict(players)[winner]]))
            losers = [name for name, _ in players if name != winner]
            say(", ".join(losers) + ",", rainbow("how about a revanche?"))
        else:
            say(rainbow("It's a draw!"), "Shall we start a new round?")
        running = ask("Hit <Enter> for yes or any other key for no: ")
    say("The game is over.")
    render()
