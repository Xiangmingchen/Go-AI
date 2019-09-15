import io
import logging
import numpy as np
import tensorflow as tf
from matplotlib import pyplot as plt
from tqdm import tqdm_notebook
from go_ai import rl_utils


def state_responses_helper(actor_critic, states, taken_actions, next_states, rewards, terminals, wins, mcts_move_probs):
    """
    Helper function for
    :param actor_critic:
    :param states:
    :param taken_actions:
    :param next_states:
    :param rewards:
    :param terminals:
    :param wins:
    :param mcts_move_probs:
    :return:
    """

    def action_1d_to_2d(action_1d, board_width):
        """
        Converts 1D action to 2D or None if it's a pass
        """
        if action_1d == board_width ** 2:
            action = None
        else:
            action = (action_1d // board_width, action_1d % board_width)
        return action

    board_size = states[0].shape[0]

    move_probs, move_vals = rl_utils.forward_pass(states, actor_critic, training=False)
    state_vals = tf.reduce_sum(move_probs * move_vals, axis=1)

    valid_moves = rl_utils.get_valid_moves(states)

    num_states = states.shape[0]
    num_cols = 4

    fig = plt.figure(figsize=(num_cols * 2.5, num_states * 2))
    for i in range(num_states):
        curr_col = 1

        plt.subplot(num_states, num_cols, curr_col + num_cols * i)
        plt.axis('off')
        plt.title('Board')
        plt.imshow(states[i][:, :, [0, 1, 4]].astype(np.float))
        curr_col += 1

        if mcts_move_probs is None:
            plt.subplot(num_states, num_cols, curr_col + num_cols * i)
            plot_move_distr('Critic', move_vals[i], valid_moves[i],
                            scalar=state_vals[i].numpy())
        else:
            plt.subplot(num_states, num_cols, curr_col + num_cols * i)
            plot_move_distr('MCTS', mcts_move_probs[i], valid_moves[i])
        curr_col += 1

        plt.subplot(num_states, num_cols, curr_col + num_cols * i)
        plot_move_distr('Actor{}'.format(' Critic' if mcts_move_probs is not None else ''),
                        move_probs[i], valid_moves[i],
                        scalar=state_vals[i].numpy().item())
        curr_col += 1

        plt.subplot(num_states, num_cols, curr_col + num_cols * i)
        plt.axis('off')
        plt.title('Taken Action: {}\n{:.0f}R {}T, {}W'
                  .format(action_1d_to_2d(taken_actions[i], board_size), rewards[i], terminals[i], wins[i]))
        plt.imshow(next_states[i][:, :, [0, 1, 4]].astype(np.float))
        curr_col += 1

    plt.tight_layout()
    return fig


def state_responses(actor_critic, replay_mem):
    """
    :param actor_critic: The model
    :param replay_mem: List of events
    :param num_samples: Prefix size of the replay memory to use
    :return: The responses of the model
    on those events
    """
    states, actions, next_states, rewards, terminals, wins, mc_pis = rl_utils.replay_mem_to_numpy(replay_mem)
    assert len(states[0].shape) == 3 and states[0].shape[0] == states[0].shape[1], states[0].shape

    fig = state_responses_helper(actor_critic, states, actions, next_states, rewards, terminals, wins, mc_pis)
    return fig


def log_to_tensorboard(summary_writer, metrics, step, replay_mem, actor_critic):
    """
    Logs metrics to tensorboard.
    Also resets keras metrics after use
    """
    with summary_writer.as_default():
        # Keras metrics
        for key, metric in metrics.items():
            tf.summary.scalar(key, metric.result(), step=step)

        reset_metrics(metrics)

        # Plot samples of states and response heatmaps
        logging.debug("Sampling heatmaps...")
        fig = state_responses(actor_critic, replay_mem)
        tf.summary.image("model heat maps", plot_to_image(fig), step=step)


def plot_move_distr(title, move_distr, valid_moves, scalar=None):
    """
    Takes in a 1d array of move values and plots its heatmap
    """
    board_size = int((len(move_distr) - 1) ** 0.5)
    plt.axis('off')
    valid_values = np.extract(valid_moves[:-1] == 1, move_distr[:-1])
    assert np.isnan(move_distr).any() == False, move_distr
    pass_val = float(move_distr[-1])
    plt.title(title + (' ' if scalar is None else ' {:.3f}S').format(scalar)
              + '\n{:.3f}L {:.3f}H {:.3f}P'.format(np.min(valid_values)
                                                   if len(valid_values) > 0 else 0,
                                                   np.max(valid_values)
                                                   if len(valid_values) > 0 else 0,
                                                   pass_val))
    plt.imshow(np.reshape(move_distr[:-1], (board_size, board_size)))


def plot_to_image(figure):
    """Converts the matplotlib plot specified by 'figure' to a PNG image and
    returns it. The supplied figure is closed and inaccessible after this call."""
    # Save the plot to a PNG in memory.
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    # Closing the figure prevents it from being displayed directly inside
    # the notebook.
    plt.close(figure)
    buf.seek(0)
    # Convert PNG buffer to TF image
    image = tf.image.decode_png(buf.getvalue(), channels=4)
    # Add the batch dimension
    image = tf.expand_dims(image, 0)
    return image


def reset_metrics(metrics):
    for key, metric in metrics.items():
        metric.reset_states()


def evaluate(go_env, policy, opponent, max_steps, num_games, mc_sims):
    win_metric = tf.keras.metrics.Mean()

    pbar = tqdm_notebook(range(num_games), desc='Evaluating against former self', leave=False)
    for episode in pbar:
        if episode % 2 == 0:
            black_won = rl_utils.pit(go_env, policy, opponent, max_steps, mc_sims)
            win = (black_won + 1) / 2

        else:
            black_won = rl_utils.pit(go_env, opponent, policy, max_steps, mc_sims)
            win = (-black_won + 1) / 2

        win_metric.update_state(win)
        pbar.set_postfix_str('{} {:.1f}%'.format(win, 100 * win_metric.result().numpy()))

    return win_metric.result().numpy()