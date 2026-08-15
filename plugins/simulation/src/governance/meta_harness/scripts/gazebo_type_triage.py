#!/usr/bin/env python3
"""Minimal rclpy type-conversion triage: subscribe to several topics."""
import os
import sys

import rclpy
from rclpy.node import Node

try:
    from nav_msgs.msg import Odometry
    print('nav_msgs.Odometry import OK', flush=True)
except Exception as e:
    print('nav_msgs.Odometry import FAIL:', e, flush=True)

try:
    from sensor_msgs.msg import Range
    print('sensor_msgs.Range import OK', flush=True)
except Exception as e:
    print('sensor_msgs.Range import FAIL:', e, flush=True)

try:
    from std_msgs.msg import String
    print('std_msgs.String import OK', flush=True)
except Exception as e:
    print('std_msgs.String import FAIL:', e, flush=True)


class Triage(Node):
    def __init__(self):
        super().__init__('triage')
        self.n = 0
        try:
            self.create_subscription(Odometry, '/bottlesumo/odom', self.cb_odom, 5)
            print('sub odom created', flush=True)
        except Exception as e:
            print('sub odom FAIL:', e, flush=True)
        try:
            self.create_subscription(Range, '/bottlesumo/edge_front', self.cb_range, 5)
            print('sub edge_front created', flush=True)
        except Exception as e:
            print('sub edge_front FAIL:', e, flush=True)

    def cb_odom(self, msg):
        self.n += 1
        print(f'ODOM#{self.n}: x={msg.pose.pose.position.x:.3f}', flush=True)
        if self.n >= 2:
            raise SystemExit(0)

    def cb_range(self, msg):
        print(f'RANGE: {msg.range:.3f}', flush=True)


def main():
    rclpy.init()
    node = Triage()
    try:
        rclpy.spin(node)
    except SystemExit:
        print('TRIAGE: odom conversion OK', flush=True)
    except Exception as e:
        print('TRIAGE FAIL:', type(e).__name__, e, flush=True)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
