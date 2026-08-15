#!/usr/bin/env python3
"""Fix DAgger C header variable names + add inference engine for firmware."""

import re
import sys


def fix_weights_file(src_path, dst_path):
    with open(src_path) as f:
        content = f.read()

    # Fix variable names to match firmware convention
    # dqn_fc0_bias → dqn_fc1_bias
    content = content.replace("dqn_fc0_bias", "dqn_fc1_bias")
    # dqn_fc1_bias (64) → dqn_fc2_bias (but only the single declaration, careful)
    # Actually: after the first fix, the second bias array was originally dqn_fc1_bias
    # Now after first fix, the first bias is dqn_fc1_bias[128] and second is dqn_fc1_bias[64]
    # We need to distinguish them. Let me use more specific patterns.

    # Reset: re-read original and do all fixes at once with regex on declarations
    content = content.replace("const float dqn_fc0_bias[", "const float dqn_fc1_bias[")

    # The second bias: originally named dqn_fc1_bias but should be dqn_fc2_bias
    # Find the second occurrence of "dqn_fc1_bias" (after the first that we just fixed)
    # Strategy: after first fix, search for "dqn_fc1_bias[" that is NOT the first occurrence
    # But simpler: just fix the original dqn_fc1_bias[64] to dqn_fc2_bias[64] FIRST, then fix fc0

    # Re-read
    with open(src_path) as f:
        content = f.read()

    # Fix fc3_weight → fc_out_weight
    content = content.replace("dqn_fc3_weight", "dqn_fc_out_weight")
    # Fix fc2_bias → fc_out_bias (the last bias, was fc2 originally)
    content = content.replace("dqn_fc2_bias", "dqn_fc_out_bias")
    # Fix fc1_bias (second occurrence, size 64) → fc2_bias
    # But wait - we need to distinguish between fc1_bias[128] and fc1_bias[64]
    # After renaming fc0→fc1, we'll have two fc1_bias arrays.
    # Better approach: rename in order from bottom up

    # Start fresh
    with open(src_path) as f:
        content = f.read()

    # Order matters: rename from last to first to avoid collisions
    # 1. dqn_fc3_weight → dqn_fc_out_weight (last weight, 704 values)
    content = content.replace("dqn_fc3_weight", "dqn_fc_out_weight")
    # 2. dqn_fc2_bias → dqn_fc_out_bias (last bias, 11 values)
    content = content.replace("dqn_fc2_bias", "dqn_fc_out_bias")
    # 3. dqn_fc1_bias → dqn_fc2_bias (second bias, 64 values)
    #    But we have TWO dqn_fc1_bias after renaming fc0.
    #    Need to identify the 64-value one specifically
    # 4. dqn_fc0_bias → dqn_fc1_bias (first bias, 128 values)

    # Step 3: Find the bias array with size 64
    content = re.sub(r"const float dqn_fc1_bias\[64\]", "const float dqn_fc2_bias[64]", content)
    # Step 4: Rename fc0 to fc1
    content = content.replace("dqn_fc0_bias", "dqn_fc1_bias")

    # Update the architecture comment
    content = content.replace(
        "// Architecture: 16→128→64→11", "// Architecture: 16→128→64→11  |  DAgger from V11 Expert"
    )

    # Add include and header comment
    header = (
        "/**\n"
        " * DQN Weights — DAgger Student (float32)\n"
        " * Trained via DAgger from V11 Rule-Based Expert\n"
        " * Auto-generated from clone_v11_dagger_fast.py\n"
        " * 16→128→64→11  |  10,944 params  |  HIL verified 46.7%\n"
        " */\n"
        '#include "dqn_weights.h"\n'
        "#include <string.h>\n\n"
    )

    # Replace the existing header
    content = re.sub(r"^//.*?\n\n", header, content, count=1, flags=re.DOTALL)
    # If no match, prepend
    if "DQN Student" not in content[:100]:
        content = header + content

    # Append inference engine
    inference = """
/* ======== Inference engine (row-major matmul) ======== */

static void matmul_and_bias(const float* input, const float* weight,
                             const float* bias, float* output,
                             int input_dim, int output_dim) {
    for (int o = 0; o < output_dim; o++) {
        float sum = bias[o];
        const float* w_row = weight + o * input_dim;
        for (int i = 0; i < input_dim; i++) {
            sum += input[i] * w_row[i];
        }
        output[o] = sum;
    }
}

void dqn_inference(const float* input, float* output) {
    float h1[128];
    float h2[64];

    // FC1: 16→128 + ReLU
    matmul_and_bias(input, dqn_fc1_weight, dqn_fc1_bias, h1, 16, 128);
    for (int i = 0; i < 128; i++) {
        if (h1[i] < 0.0f) h1[i] = 0.0f;
    }

    // FC2: 128→64 + ReLU
    matmul_and_bias(h1, dqn_fc2_weight, dqn_fc2_bias, h2, 128, 64);
    for (int i = 0; i < 64; i++) {
        if (h2[i] < 0.0f) h2[i] = 0.0f;
    }

    // FC_OUT: 64→11 (linear)
    matmul_and_bias(h2, dqn_fc_out_weight, dqn_fc_out_bias, output, 64, 11);
}
"""

    content += inference

    with open(dst_path, "w") as f:
        f.write(content)

    # Verify variable names
    var_pattern = r"const float (dqn_\w+)\["
    vars_found = re.findall(var_pattern, content)
    print(f"Variables in output: {vars_found}")
    print(f"File size: {len(content)} bytes")
    print(f"Written to: {dst_path}")


if __name__ == "__main__":
    src = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/home/ivy/bottlesumo_pi/simulation/dqn_weights_dagger.c"
    )
    dst = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "/home/ivy/bottlesumo_pi/firmware/stm32_mcu/src/dqn_weights_fixed.c"
    )
    fix_weights_file(src, dst)
