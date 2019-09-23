from sklearn.preprocessing import normalize
import numpy as np
import gym

GoGame = gym.make('gym_go:go-v0', size=0).gogame


class Node:
    def __init__(self, parentaction, action_probs, state_value, state):
        '''
        Args:
            parent (?Node): parent Node
            action_probs (tensor): the policy action probs (flattened)
            state_value (float): the state value of this node
            state: state of the game as a numpy array
        '''
        if parentaction is not None:
            self.parent = parentaction[0]
            self.parent.children[parentaction[1]] = self
        else:
            self.parent = None

        self.height = self.parent.height + 1 if self.parent is not None else 0
        # 1d array of the size that can hold the moves including pass,
        # initially all None
        assert state.shape[1] == state.shape[2]
        board_size = state.shape[1]
        self.children = np.empty(board_size ** 2 + 1, dtype=object)
        self.action_probs = action_probs
        self.state = state
        self.turn = GoGame.get_turn(state)
        self.terminal = GoGame.get_game_ended(state)
        # number of time this node was visited
        self.N = 0
        self.V = state_value  # the evaluation of this node (value)
        self.Q_sum = 0

    def is_leaf(self):
        if self.N == 1:
            return True
        real_children = filter(lambda child: child is not None, self.children)
        return sum(map(lambda child: child.N, real_children)) <= 0

    def visited(self):
        return self.N > 0

    @property
    def cached_children(self):
        return (self.children != None).any()

    def avg_Q(self, move):
        child = self.children[move]
        avg_Q = (child.V.item() + child.Q_sum) / (1 + self.N)
        return -avg_Q

    def Qs(self):
        valid_moves = GoGame.get_valid_moves(self.state)
        Qs = [(self.avg_Q(move) if valid_moves[move] else 0) for move in range(GoGame.get_action_size(self.state))]
        return np.array(Qs)

    def back_propagate(self, value_incre):
        '''
        Description:
            Recursively increases the number visited by 1 and increase the
            V_sum by value increment from this node up to the root node.
        '''
        self.N += 1
        self.Q_sum += value_incre
        if self.parent is not None:
            self.parent.back_propagate(-value_incre)

    def __str__(self):
        return '{} {}H {}/{}VVS {}N'.format(np.sum(self.state[[0, 1]], axis=0), self.height, self.V, self.Q_sum, self.N)


class MCTree:
    # Environment ot call the stateless go logic APIs

    def __init__(self, state, forward_func):
        """
        :param state: Starting state
        :param forward_func: Takes in a batch of states and returns action
        probs and state values
        """
        self.forward_func = forward_func

        action_probs, state_value = forward_func(state[np.newaxis])
        action_probs, state_value = action_probs[0], state_value[0]

        self.root = Node(None, action_probs, state_value, state)
        assert not self.root.visited()
        self.root.back_propagate(self.root.V)

        assert state.shape[1] == state.shape[2]
        self.board_size = state.shape[1]
        self.action_size = GoGame.get_action_size(self.root.state)

    def get_action_probs(self, max_num_searches, temp):
        '''
        Description:
            Select a child node that maximizes Q + U,
        Args:
            max_num_searches (int): maximum number of searches performed
            temp (number): temperature constant
        Returns:
            pi (1d np array): the search probabilities
            num_search (int): number of search performed
        '''
        assert max_num_searches > 0
        num_search = 0
        while num_search < max_num_searches:
            curr_node = self.root
            # keep going down the tree with the best move
            while curr_node.visited() and not curr_node.terminal:
                curr_node, move = self.select_best_child(curr_node)

            curr_node.back_propagate(curr_node.V)

            # increment search counter
            num_search += 1

        N = list(map(lambda node: node.N if node is not None else 0, self.root.children))
        N = np.array(N)
        if temp > 0:
            pi = normalize([N ** (1 / temp)], norm='l1')[0]
        else:
            best_actions = (N == np.max(N))
            pi = normalize(best_actions[np.newaxis], norm='l1')[0]

        return pi

    def select_best_child(self, node, u_const=1):
        """
        :param node:
        :param u_const: 'Exploration' factor of U
        :return: the child that
            maximizes Q + U, where Q = V_sum / N, and
            U = U_CONST * P / (1 + N), where P is action value.
            forward_func action probs
        """
        if not node.cached_children:
            self.cache_children(node)

        valid_moves = GoGame.get_valid_moves(node.state)
        valid_move_idcs = np.argwhere(valid_moves > 0).flatten()
        best_move = None
        max_UCB = np.NINF  # negative infinity
        # calculate Q + U for all children
        for move in valid_move_idcs:
            Q = node.avg_Q(move)
            child = node.children[move]
            Nsa = child.N
            Psa = node.action_probs[move]
            U = u_const * Psa * np.sqrt(node.N) / (1 + Nsa)

            # UCB: Upper confidence bound
            if Q + U > max_UCB:
                max_UCB = Q + U
                best_move = move

        if best_move is None:
            raise Exception("MCTS: move shouldn't be None, please debug")

        return node.children[best_move], best_move

    def cache_children(self, node):
        """
        Caches children for analysis by the forward function.
        Cached children have zero visit count, N = 0
        :param node:
        :return:
        """
        if node.terminal:
            return

        valid_move_idcs = GoGame.get_valid_moves(node.state)
        valid_move_idcs = np.argwhere(valid_move_idcs > 0).flatten()

        batch_pis, batch_qvals, batch_canonical_children = get_immediate_lookahead(node.state[np.newaxis],
                                                                                   self.forward_func)
        for idx, move in enumerate(valid_move_idcs):
            Node((node, move), batch_pis[0][idx], batch_qvals[0][idx], batch_canonical_children[0][idx])

    def step(self, action):
        '''
        Move the root down to a child with action. Throw away all nodes
        that are not in the child subtree. If such child doesn't exist yet,
        expand it.
        '''
        child = self.root.children[action]
        if child is None:
            next_state = GoGame.get_next_state(self.root.state, action)
            next_turn = GoGame.get_turn(next_state)
            canonical_state = GoGame.get_canonical_form(next_state, next_turn)
            action_probs, state_value = self.forward_func(canonical_state[np.newaxis])
            action_probs, state_value = action_probs[0], state_value[0]
            # Set parent to None because we know we're going to set it as root
            child = Node(None, action_probs, state_value, next_state)

        self.root = child
        self.root.parent = None
        if not self.root.visited():
            self.root.back_propagate(self.root.V)

    def reset(self):
        initial_state = GoGame.get_init_board(self.board_size)
        self.__init__(initial_state, self.forward_func)

    def __str__(self):
        queue = [self.root]
        str_builder = ''
        while len(queue) > 0:
            curr_node = queue.pop(0)
            for child in curr_node.children:
                if child is not None:
                    queue.append(child)
            str_builder += '{}\n\n'.format(curr_node)

        return str_builder[:-2]


def get_immediate_lookahead(states, forward_func):
    """
    :param states:
    :param forward_func:
    :return: policies and qvals of children of every state
    (batch size x children x pi), (batch size x children x value)
    """

    def canonical_winning(canonical_state):
        my_area, opp_area = GoGame.get_areas(canonical_state)
        if my_area > opp_area:
            winning = 1
        elif my_area < opp_area:
            winning = -1
        else:
            winning = 0

        return winning

    # Get all children states
    canonical_next_states = []
    for state in states:
        valid_moves = GoGame.get_valid_moves(state)
        valid_move_idcs = np.argwhere(valid_moves > 0).flatten()
        for move in valid_move_idcs:
            next_state = GoGame.get_next_state(state, move)
            next_turn = GoGame.get_turn(next_state)
            canonical_next_state = GoGame.get_canonical_form(next_state, next_turn)
            canonical_next_states.append(canonical_next_state)

    # Get network responses on children
    canonical_next_states = np.array(canonical_next_states)
    canonical_pis, canonical_next_vals = forward_func(canonical_next_states)

    curr_idx = 0
    batch_qvals = []
    batch_pis = []
    for state in states:
        valid_moves = GoGame.get_valid_moves(state)
        Qs = []
        children_pis = []
        for move in range(GoGame.get_action_size(state)):
            if valid_moves[move]:
                canonical_next_state = canonical_next_states[curr_idx]
                terminal = GoGame.get_game_ended(canonical_next_state)
                winning = canonical_winning(canonical_next_state)
                val = (1 - terminal) * canonical_next_vals[curr_idx] + (terminal) * winning
                Qs.append(-val)
                children_pis.append(canonical_pis[curr_idx])
                curr_idx += 1
            else:
                Qs.append(0)

        batch_qvals.append(Qs)
        batch_pis.append(children_pis)

    assert curr_idx == len(canonical_next_vals), (curr_idx, len(canonical_next_vals))
    assert curr_idx == len(canonical_pis), (curr_idx, len(canonical_pis))
    return np.array(batch_pis), np.array(batch_qvals), canonical_next_states
