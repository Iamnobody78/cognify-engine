#!/usr/bin/env python3
"""Hexdump raw Range message to determine exact CDR layout."""
import os
import sys

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range


class Dump(Node):
    def __init__(self):
        super().__init__('dump')
        self.n = 0
        self.create_subscription(Range, '/bottlesumo/edge_front', self.cb, 5, raw=True)

    def cb(self, raw):
        self.n += 1
        if self.n > 3:
            raise SystemExit(0)
        print(f'len={len(raw)}')
        for i in range(0, len(raw), 8):
            chunk = raw[i:i+8]
            hexs = ' '.join(f'{b:02x}' for b in chunk)
            asci = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f'  {i:3d}: {hexs:<24} {asci}')


def main():
    rclpy.init()
    node = Dump()
    try:
        rclpy.spin(node)
    except SystemExit:
        print('DUMP DONE')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
