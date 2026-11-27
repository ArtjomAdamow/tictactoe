"""
    Scripted games for the turn engine of game.py, no server needed: python -m unittest test_game
"""
import random
import unittest

from game import Game


def make(computers=('C',), timeout=None, side=3, z=3):
    players = [('A', 'X'), ('B', 'O'), ('C', 'Z')]
    return Game(players, computers, side, z, timeout)


class TurnEngine(unittest.TestCase):
    def setUp(self):
        random.seed(1)

    def test_lobby_does_not_step(self):
        game = make()
        self.assertEqual(game.state, 'lobby')
        self.assertFalse(game.step(0))

    def test_human_waits_then_moves_queued(self):
        game = make(computers=())
        game.start(0)
        first = game.order[0]
        self.assertFalse(game.step(1))
        game.queue_move(first, 5)
        self.assertTrue(game.step(1))
        self.assertEqual(game.board[5], game.symbol_of(first))
        self.assertEqual(game.turn, 1)

    def test_queued_field_taken_meanwhile_is_cleared(self):
        game = make(computers=())
        game.start(0)
        first, second, third = game.order
        game.queue_move(third, 5)
        game.queue_move(first, 5)
        game.step(1)
        self.assertNotIn(third, game.queue)
        with self.assertRaises(ValueError):
            game.queue_move(second, 5)

    def test_timeout_computer_moves_and_player_is_afk(self):
        game = make(computers=(), timeout=10)
        game.start(0)
        name = game.order[0]
        self.assertFalse(game.step(9))
        self.assertTrue(game.step(10))
        self.assertEqual(len(game.free_fields()), 8)
        self.assertEqual(game.turn_started, 10)
        self.assertIn(name, game.afk)
        self.assertIn("%s: The party moves on, the computer made your move." % name, game.messages)
        self.assertIn("Player %s seems to be AFK." % name, game.messages)

    def test_afk_moves_at_once_until_the_player_acts(self):
        game = make(computers=(), timeout=10)
        game.start(0)
        name = game.order[0]
        game.step(10)
        game.step(20)
        game.step(30)                                       # the others time out, too, a new round begins
        self.assertEqual(game.afk, set(game.order))
        self.assertTrue(game.step(30))                      # afk: moves without waiting
        game.queue_move(name, game.free_fields()[0])
        self.assertNotIn(name, game.afk)

    def test_afk_player_is_dropped_out_by_the_revanche(self):
        game = make(computers=(), timeout=10)
        game.start(0)
        name = game.order[0]
        game.step(10)
        for _ in range(20):
            if game.state == 'over':
                break
            game.step(game.turn_started + 10)
        self.assertEqual(game.state, 'over')
        self.assertIn(name, game.afk)
        game.start(0)
        self.assertNotIn(name, game.afk)
        self.assertIn(name, game.computers)
        self.assertIn("Player %s dropped out, the computer took over." % name, game.messages)

    def test_timeout_is_capped_and_never_off(self):
        self.assertEqual(make(timeout=None).timeout, 60)
        self.assertEqual(make(timeout=600).timeout, 60)
        self.assertEqual(make().timeout, 60)

    def test_computers_play_to_the_end_and_revanche(self):
        game = make(computers=('A', 'B', 'C'))
        game.start(0)
        for _ in range(100):
            if not game.step(0):
                break
        self.assertEqual(game.state, 'over')
        self.assertTrue(game.result)
        self.assertEqual(sum(game.scores.values()) + game.draws, 1)
        game.start(0)
        self.assertEqual(game.state, 'playing')
        self.assertEqual(len(game.free_fields()), 9)

    def test_order_is_reshuffled_every_round(self):
        game = make(computers=('A', 'B', 'C'), side=9, z=9)
        game.start(0)
        orders = set()
        for _ in range(60):
            orders.add(tuple(game.order))
            game.step(0)
        self.assertGreater(len(orders), 1)
        self.assertEqual(sorted(game.order), ['A', 'B', 'C'])

    def test_pause_resume_and_timeout(self):
        game = make(computers=(), timeout=10)
        game.start(0)
        game.pause()
        self.assertFalse(game.step(100))
        game.resume(100)
        self.assertFalse(game.step(105))
        self.assertTrue(game.step(110))

    def test_dropout_and_take_over(self):
        game = make(computers=())
        game.start(0)
        game.queue_move('A', 1)
        game.to_computer('A')
        self.assertNotIn('A', game.queue)
        self.assertIn('A', game.computers)
        game.take_over('A', 'Zed', '#')
        self.assertEqual(game.symbol_of('Zed'), '#')
        self.assertIn('Zed', game.order)
        self.assertIn('Zed', game.scores)
        self.assertNotIn('Zed', game.computers)
        with self.assertRaises(ValueError):
            game.take_over('Zed', 'Q', '#')              # not a computer seat any more
        with self.assertRaises(ValueError):
            game.take_over('B', 'Q', '#')

    def test_take_over_keeps_marks_on_board(self):
        game = make(computers=('A', 'B', 'C'))
        game.start(0)
        game.step(0)
        mover = game.order[0]
        field = next(k for k, v in game.board.items() if v == game.symbol_of(mover))
        game.take_over(mover, 'Zed', '#')
        self.assertEqual(game.board[field], '#')


if __name__ == '__main__':
    unittest.main()
