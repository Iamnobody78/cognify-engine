/*
 * DQN Weights Header — DAgger Student
 * 16→128→64→11  |  10,944 float32 params
 * Trained via DAgger from V11 Rule-Based Expert
 * HIL verified: 46.7% win rate (14/30)
 *
 * Architecture:
 *   Input:  16-dim normalized observation
 *   Hidden1: 128-dim FC + ReLU
 *   Hidden2: 64-dim FC + ReLU
 *   Output:  11-dim Q-values (no activation)
 *
 * Actions: IDLE, FWD, BACK, LEFT, RIGHT, FWD_LEFT, FWD_RIGHT,
 *          BACK_LEFT, BACK_RIGHT, ATTACK, ESTOP
 */
#ifndef DQN_WEIGHTS_H
#define DQN_WEIGHTS_H

#ifdef __cplusplus
extern "C" {
#endif

#define OBS_DIM     16
#define HIDDEN1_DIM 128
#define HIDDEN2_DIM 64
#define NUM_ACTIONS 11
/* For backward compat with code using HIDDEN_DIM */
#define HIDDEN_DIM  HIDDEN1_DIM

/* Weight arrays (defined in dqn_weights.c) */
extern const float fc1_weight[OBS_DIM][HIDDEN1_DIM];
extern const float fc1_bias[HIDDEN1_DIM];
extern const float fc2_weight[HIDDEN1_DIM][HIDDEN2_DIM];
extern const float fc2_bias[HIDDEN2_DIM];
extern const float fc3_weight[HIDDEN2_DIM][NUM_ACTIONS];
extern const float fc3_bias[NUM_ACTIONS];

/**
 * DQN inference — forward pass through 3-layer MLP
 * @param input  16-element float array (normalized observation)
 * @param output 11-element float array (Q-values for each action)
 */
void dqn_inference(const float* input, float* output);

#ifdef __cplusplus
}
#endif

#endif /* DQN_WEIGHTS_H */
