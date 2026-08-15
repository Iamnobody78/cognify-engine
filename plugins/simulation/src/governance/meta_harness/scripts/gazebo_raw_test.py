#!/usr/bin/env python3
"""Test raw subscription for Range (bypass pybind11 conversion layer)."""
import os
import struct
import sys

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range


class RawTest(Node):
    def __init__(self):
        super().__init__('raw_test')
        self.n = 0
        # raw=True: callback receives raw bytes, no pybind11 conversion
        self.create_subscription(Range, '/bottlesumo/edge_front', self.cb, 5, raw=True)

    def cb(self, raw_bytes):
        self.n += 1
        try:
            off = 12
            (flen,) = struct.unpack_from('<I', raw_bytes, off)
            off += 4 + flen          # skip frame_id chars (len includes null)
            rad = raw_bytes[off]
            off = (off + 1 + 3) & ~3  # align to 4 for floats
            fov, mn, mx, rng = struct.unpack_from('<ffff', raw_bytes, off)
            print(f'RAW#{self.n}: len={len(raw_bytes)} flen={flen} rad={rad} '
                  f'fov={fov:.3f} min={mn:.4f} max={mx:.4f} range={rng:.4f}', flush=True)
            if self.n >= 2:
                raise SystemExit(0)
        except Exception as e:
            print(f'RAW parse fail at n={self.n}: {e} len={len(raw_bytes)}', flush=True)


def main():
    rclpy.init()
    node = RawTest()
    try:
        rclpy.spin(node)
    except SystemExit:
        print('RAW SUBSCRIPTION OK', flush=True)
    except Exception as e:
        print('RAW FAIL:', type(e).__name__, e, flush=True)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
