"""
    Scripted requests for server.py with a fake clock, no network: python -m unittest test_server
"""
import random
import unittest
from unittest import mock

import calibrate
import server


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Api(unittest.TestCase):
    def setUp(self):
        random.seed(1)
        self.clock = Clock()
        self.app = server.create_app(self.clock, loop=False)
        self.srv = self.app.server
        self.http = self.app.test_client()
        self.tokens = []                # everybody who joined; run_ticks polls for them like a browser

    def post(self, path, **data):
        return self.http.post('/' + path, json=data)

    def join(self, name, symbol):
        response = self.post('join', name=name, symbol=symbol)
        self.assertEqual(response.status_code, 200)
        self.tokens.append(response.json['token'])
        return response.json['token']

    def run_ticks(self, count, step=server.COMPUTER_DELAY):
        for _ in range(count):
            self.clock.now += step
            self.poll()
            self.srv.tick()

    def poll(self, only=None):
        for token in only or self.tokens:
            self.state(token)

    def state(self, token=None):
        return self.http.get('/state', query_string={'token': token}).json


class Lobby(Api):
    def test_first_is_host_and_edit(self):
        a = self.join('Ann', 'X')
        b = self.join('Bob', 'O')
        people = self.state(a)['people']
        self.assertEqual([p['host'] for p in people], [True, False])
        self.assertEqual(self.post('join', token=b, name='Ann', symbol='O').status_code, 400)
        self.assertEqual(self.post('join', token=b, name='Bobby', symbol='Y').status_code, 200)
        self.assertEqual(self.state(b)['you']['name'], 'Bobby')

    def test_only_host_starts(self):
        a, b = self.join('Ann', 'X'), self.join('Bob', 'O')
        self.assertEqual(self.post('start', token=b).status_code, 403)
        self.assertEqual(self.post('start', token=a).status_code, 200)
        game = self.state(a)['game']
        self.assertEqual(game['state'], 'playing')
        self.assertEqual(len(game['players']), 2)

    def test_extra_computers_and_bad_setup(self):
        a = self.join('Ann', 'X')
        self.assertEqual(self.post('start', token=a).status_code, 400)          # one player alone
        self.assertEqual(self.post('start', token=a, computers=2, side=2).status_code, 400)
        self.assertEqual(self.post('start', token=a, computers=2).status_code, 200)
        players = self.state(a)['game']['players']
        self.assertEqual([p['computer'] for p in players], [False, True, True])
        self.assertEqual(len({p['symbol'] for p in players}), 3)


class Running(Api):
    def start(self, computers=1):
        a, b = self.join('Ann', 'X'), self.join('Bob', 'O')
        self.post('start', token=a, computers=computers)
        return a, b

    def test_queue_and_computer_pace(self):
        a, b = self.start()
        game = self.srv.game
        self.assertEqual(self.post('queue', token=a, field=99).status_code, 400)
        self.post('queue', token=a, field=1)
        self.post('queue', token=b, field=2)
        self.srv.tick()                                       # no computer is due yet at the same instant
        self.run_ticks(10)
        board = self.state(a)['game']['board']
        self.assertEqual(board['1'], 'X')
        self.assertEqual(board['2'], 'O')
        self.assertTrue(self.state(a)['messages'])
        self.assertLessEqual(len(self.srv.log), server.LOG_SIZE)
        self.assertEqual(game.messages, [])                   # drained into the log

    def test_timeout_makes_the_human_afk(self):
        a, b = self.start()
        self.run_ticks(5)
        self.clock.now += 61
        self.poll()
        self.srv.tick()
        self.assertTrue(any(p['afk'] for p in self.state(a)['game']['players']))

    def test_claim_and_leave(self):
        a, b = self.start()
        c = self.join('Cy', 'Z')
        self.assertEqual(self.post('claim', token=c, seat='Computer 1').status_code, 200)
        self.assertEqual(self.state(c)['you']['seat'], 'Cy')
        self.post('leave', token=a)
        self.assertTrue(self.state(b)['you']['host'])        # the host moved on
        game = self.state(b)['game']
        self.assertTrue(next(p for p in game['players'] if p['name'] == 'Ann')['computer'])

    def test_last_one_leaves_pauses_and_join_resumes(self):
        a, b = self.start()
        self.post('leave', token=a)
        self.post('leave', token=b)
        self.assertEqual(self.state()['game']['state'], 'paused')
        self.run_ticks(5)
        self.assertEqual(self.state()['game']['state'], 'paused')
        c = self.join('Cy', 'Z')
        self.assertEqual(self.state(c)['game']['state'], 'playing')
        self.assertTrue(self.state(c)['you']['host'])
        self.assertEqual(self.post('start', token=c).status_code, 400)             # the choice: new game needs new: true
        self.assertEqual(self.post('start', token=c, new=True, computers=1).status_code, 200)
        self.assertEqual([p['name'] for p in self.state(c)['game']['players']][0], 'Cy')


class Presence(Api):
    def test_silence_drops_and_token_returns(self):
        a, b = self.join('Ann', 'X'), self.join('Bob', 'O')
        self.post('start', token=a)
        for _ in range(10):                                  # only Bob keeps polling
            self.clock.now += 1
            self.poll([b])
            self.srv.tick()
        game = self.state(b)['game']
        self.assertTrue(next(p for p in game['players'] if p['name'] == 'Ann')['computer'])
        self.assertTrue(self.state(b)['you']['host'])        # the host moved on
        self.assertEqual(self.state(a)['you'], None)
        self.assertEqual(self.post('join', token=a).status_code, 200)    # reconnect by token
        self.assertEqual(self.state(a)['you']['seat'], 'Ann')
        self.assertFalse(next(p for p in self.state(a)['game']['players'] if p['name'] == 'Ann')['computer'])

    def test_no_reconnect_after_replacement(self):
        a, b = self.join('Ann', 'X'), self.join('Bob', 'O')
        self.post('start', token=a)
        self.post('leave', token=a)
        self.post('start', token=b, new=True, computers=1)
        self.assertEqual(self.post('join', token=a, name='Ann', symbol='X').json['token'] != a, True)

    def test_last_human_silent_pauses(self):
        a = self.join('Ann', 'X')
        self.post('start', token=a, computers=1)
        self.clock.now += 6
        self.srv.tick()
        self.assertEqual(self.srv.game.state, 'paused')
        self.assertEqual(self.post('join', token=a).status_code, 200)
        self.assertEqual(self.srv.game.state, 'playing')
        self.assertEqual(self.state(a)['you']['host'], True)


class AutoStart(Api):
    def finish(self, a):
        """
            Plays until the game is over
        """
        for _ in range(200):
            if self.srv.game.state == 'over':
                return
            self.run_ticks(1)
        self.fail("the game did not end")

    def test_over_waits_for_revanche_while_a_human_plays(self):
        a = self.join('Ann', 'X')
        self.post('start', token=a, computers=1)
        for _ in range(200):
            self.post('queue', token=a, field=self.srv.game.free_fields()[0])
            self.run_ticks(1)
            if self.srv.game.state == 'over':
                break
        self.assertEqual(self.srv.game.state, 'over')
        self.run_ticks(5)
        self.assertEqual(self.srv.game.state, 'over')       # a human is seated, the host decides
        self.assertEqual(self.post('revanche', token=a).status_code, 200)
        self.assertEqual(self.srv.game.state, 'playing')

    def test_over_restarts_at_once_without_humans(self):
        a = self.join('Ann', 'X')
        self.post('start', token=a, computers=1)
        self.post('leave', token=a)                         # the last human drops out, a watcher keeps the lobby alive
        w = self.join('Wim', 'W')
        self.assertEqual(self.state(w)['game']['state'], 'playing')
        self.finish(w)
        wins = sum(p['score'] for p in self.state(w)['game']['players']) + self.srv.game.draws
        self.assertEqual(wins, 1)
        self.run_ticks(2)
        self.assertEqual(self.srv.game.state, 'playing')    # next game without waiting for a revanche
        self.assertEqual(wins, sum(p['score'] for p in self.state(w)['game']['players']) + self.srv.game.draws)

    def test_no_restart_while_nobody_is_in_the_lobby(self):
        a = self.join('Ann', 'X')
        self.post('start', token=a, computers=1)
        self.post('leave', token=a)
        self.assertEqual(self.srv.game.state, 'paused')
        self.run_ticks(50)
        self.assertEqual(self.srv.game.state, 'paused')


class AutoSide(Api):
    def setUp(self):
        super().setUp()
        self.srv.simulate = True

    def test_stored_recommendation_is_used(self):
        with mock.patch.object(calibrate, 'recommend', return_value=(7, True)):
            self.assertEqual(self.srv.auto_side(2, 3), 7)

    def test_recommendation_stays_inside_the_limits(self):
        with mock.patch.object(calibrate, 'recommend', return_value=(99, True)):
            self.assertEqual(self.srv.auto_side(2, 3), server.MAX_SIDE)

    def test_missing_data_uses_the_formula_and_simulates_once(self):
        with mock.patch.object(calibrate, 'recommend', return_value=None),                 mock.patch.object(server.threading, 'Thread') as thread:
            self.assertEqual(self.srv.auto_side(2, 3), server.min_side(2, 3))
            self.assertEqual(self.srv.auto_side(2, 3), server.min_side(2, 3))
            self.assertEqual(thread.call_count, 1)

    def test_auto_side_sticks_and_may_be_below_the_formula(self):
        a = self.join('Ann', 'X')
        with mock.patch.object(calibrate, 'recommend', return_value=(3, True)):
            self.assertEqual(self.post('start', token=a, computers=3, z=3, side='').status_code, 200)
            self.assertEqual(self.srv.game.side, 3)
            self.assertLess(self.srv.game.side, server.min_side(4, 3))
            self.assertIsNone(self.state(a)['setup']['side'])
            self.assertEqual(self.post('start', token=a, new=True).status_code, 200)
            self.assertIsNone(self.state(a)['setup']['side'])

    def test_tests_never_simulate(self):
        self.srv.simulate = False
        with mock.patch.object(calibrate, 'recommend') as recommend:
            self.assertEqual(self.srv.auto_side(2, 3), server.min_side(2, 3))
            recommend.assert_not_called()


if __name__ == '__main__':
    unittest.main()
