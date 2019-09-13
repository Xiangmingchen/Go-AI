import unittest
import gym
import numpy as np
import mcts

def action_2d_to_1d(action_2d, board_width):
    if action_2d is None:
        action_1d = board_width**2
    else:
        action_1d = action_2d[0] * board_width + action_2d[1]
    return action_1d

class TestMCTS(unittest.TestCase):

    def setUp(self) -> None:
        self.env = gym.make('gym_go:go-v0', size=3, reward_method='real')
        self.action_length = self.env.size**2 + 1
        mcts.U_CONST = 1
        mcts.TEMP_CONST = 1

    def tearDown(self) -> None:
        self.env.close()

    def test_one_step_search(self):
        '''
        This tests a simple one step search
        _,_,_    B,_,_                      1,0,0
        _,_,_ => _,_,_     should return    0,0,0
        _,_,_    _,_,_                      0,0,0
        '''
        def mock_forward_func(state):
            '''
            Empty board:
                action probs: 1 at the top left corner (0,0)
                state value: 0 (50% chance of wining)
            After (0,0) is black and nothing else:
                action probs: 1 at (0, 1)
                state value: 1
            '''
            action_probs = np.zeros(self.action_length)
            # empty board
            if np.count_nonzero(state[0:2]) == 0:
                action_probs[0] = 1
                state_value = 0
            # black at (0,0)
            elif state[1,0,0] == 1 and np.count_nonzero(state[1]) == 1 \
                and np.count_nonzero(state[0]) == 0:
                    idx = action_2d_to_1d((0, 1), self.env.size)
                    action_probs[idx] = 1
                    state_value = 1
            else:
                raise Exception("Unexpected state", state)
            return action_probs, state_value

        tree = mcts.MCTree(self.env.get_state(), mock_forward_func)
        # only perform one search, should only reach 1 state
        pi, num_search = tree.get_action_probs(1, 1)
        # the first move should have pi = 1
        self.assertEqual(pi[0], 1)
        # the rest of the moves should have pi = 0
        for i in range(1, self.action_length):
            self.assertEqual(pi[i], 0)
        self.assertEqual(num_search, 1)

    def test_two_step_search(self):
        '''
        This tests a simple two-step search
        _,_,_    B,_,_    B,W,_                     1,0,0
        _,_,_ => _,_,_ => _,_,_    should return    0,0,0
        _,_,_    _,_,_    _,_,_                     0,0,0
        '''
        def mock_forward_func(state):
            '''
            Empty board:
                action probs: 1 at the top left corner (0,0)
                state value: 0
            After (0,0) is black and nothing else:
                action probs: 1 at (0, 1)
                state value: -1 (white's perspective)
            When (0,0) is black, (0,1) is white:
                action probs: 1 at (1, 0)
                state value: 0.5
            As opponent, (0,0) is white:
                action probs: 1 at (0, 1)
                state value: ??
            '''
            action_probs = np.zeros(self.action_length)
            # empty board
            if np.count_nonzero(state[0:2]) == 0:
                action_probs[0] = 1
                state_value = 0
            elif np.count_nonzero(state[0:2, 0, 0]) == 1 and np.count_nonzero(state[0:2, 0, 1]) == 1:
                idx = action_2d_to_1d((1, 0), self.env.size)
                action_probs[idx] = 1
                state_value = 0.5
            elif np.count_nonzero(state[0:2,0,0]) == 1:
                idx = action_2d_to_1d((0, 1), self.env.size)
                action_probs[idx] = 1
                state_value = -1
            # unexpected states
            else:
                print('Tree:\n{}\n\nState:\n{}'.format(tree, state))
                raise Exception("Unexpected state")
            return action_probs, state_value

        tree = mcts.MCTree(self.env.get_state(), mock_forward_func)
        pi, num_search = tree.get_action_probs(2, 1)
        # the first move should have pi = 2
        self.assertEqual(pi[0], 1)
        # the rest of the moves should have pi = 0
        for i in range(1, self.action_length):
            self.assertEqual(pi[i], 0)

        # test V_sum, V and N to be expected values
        self.assertEqual(tree.root.V_sum, 1.5)
        self.assertEqual(tree.root.V, 0)
        self.assertEqual(tree.root.N, 3)

        black_node = tree.root.children[0]
        self.assertEqual(black_node.V_sum, 1.5)
        self.assertEqual(black_node.V, 1)
        self.assertEqual(black_node.N, 2)

        white_node = black_node.children[action_2d_to_1d((0, 1), self.env.size)]
        self.assertEqual(white_node.V_sum, 0.5)
        self.assertEqual(white_node.V, 0.5)
        self.assertEqual(white_node.N, 1)

    def test_two_branch_search(self):
        '''
        This tests a two branch search, search 3 times
        .5,.5,__    B,_,_
        __,__,__ => _,_,_   value = 0
        __,__,__    _,_,_

                \   _,B,_                                  .33,.66,0
                 \> _,_,_   value = 1     should return      0,  0,0
                    _,_,_                                    0,  0,0
        '''
        move_01 = action_2d_to_1d((0, 1), self.env.size)
        move_10 = action_2d_to_1d((1, 0), self.env.size)
        def mock_forward_func(state):
            '''
            Empty board:
                action probs: 0.5 for (0,0) and (0,1)
                state value: 0
            After (0,0) is black and nothing else:
                action probs: 1 at (0, 1) # shouldn't matter
                state value: 0
            When (0,1) is black and nothing else:
                action probs: 1 at (1, 0) # shouldn't matter
                state value: -1 # white's perspective
            '''
            action_probs = np.zeros(self.action_length)
            # empty board
            if np.count_nonzero(state[:2]) == 0:
                action_probs[0] = 0.5
                action_probs[move_01] = 0.5
                state_value = 0
            # opponent/self at (0,1)/(0,0), for leaf node
            elif np.count_nonzero(state[:2, 0, :1]) == 2:
                action_probs[move_10] = 1
                state_value = 0
            # opponent at (0,0)
            elif np.count_nonzero(state[:2, 0, 0]) == 1:
                    action_probs[move_01] = 1
                    state_value = 0
            # opponent at (0,1)
            elif np.count_nonzero(state[:2, 0, 1]) == 1:
                    action_probs[0] = 1
                    state_value = -1
            # unexpected states
            else:
                raise Exception("Unexpected state", state)
            return action_probs, state_value

        tree = mcts.MCTree(self.env.get_state(), mock_forward_func)
        pi, num_search = tree.get_action_probs(3, 1)
        # check pi
        self.assertEqual(pi[0], 1/3, tree)
        self.assertEqual(pi[move_01], 2/3)
        # the rest of the moves should have pi = 0
        for i in range(2, self.action_length):
            self.assertEqual(pi[i], 0)

        return tree


    def test_end_of_game(self):
        '''
        Tests that two player pass
        '''
        move_pass = action_2d_to_1d(None, self.env.size)
        def mock_forward_func(state):
            '''
            Empty board:
                action probs: 1 for pass
                state value: 0
            '''
            action_probs = np.zeros(self.action_length)
            # empty board
            if np.count_nonzero(state[:2]) == 0:
                action_probs[move_pass] = 1
                state_value = 0
            # unexpected states
            else:
                raise Exception("Unexpected state", state[:2])
            return action_probs, state_value

        tree = mcts.MCTree(self.env.get_state(), mock_forward_func)
        pi, num_search = tree.get_action_probs(3, 1)
        # check pi
        self.assertEqual(pi[move_pass], 1)
        # the rest of the moves should have pi = 0
        for i in range(0, self.action_length - 1):
            self.assertEqual(pi[i], 0)

    def test_tree_step(self):
        tree = self.test_two_branch_search()
        move_01 = action_2d_to_1d((0, 1), self.env.size)
        tree.step(move_01)
        turn = self.env.gogame.get_turn(tree.root.state)
        self.assertEqual(self.env.gogame.get_canonical_form(tree.root.state, turn)[1][0, 1], 1)
        

if __name__ == '__main__':
    unittest.main()
