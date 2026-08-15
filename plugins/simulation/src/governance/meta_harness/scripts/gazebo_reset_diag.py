#!/usr/bin/env python3
"""Diagnose post-reset_world robot behavior: does cmd_vel still drive odom?"""
import os
import subprocess
import sys
import time

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist


class ResetDiag(Node):
    def __init__(self):
        super().__init__('reset_diag')
        self.pose = None
        self.pub = self.create_publisher(Twist, '/bottlesumo/cmd_vel', 5)
        self.create_subscription(Odometry, '/bottlesumo/odom', self.on_odom, 5)

    def on_odom(self, msg):
        self.pose = msg.pose.pose

    def reset(self):
        r = subprocess.run(['ros2', 'service', 'call', '/reset_world',
                            'std_srvs/srv/Empty', '{}'],
                           capture_output=True, timeout=15)
        return r.returncode == 0

    def run(self):
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
        print(f'PRE-RESET pose=({self.pose.position.x:.4f},{self.pose.position.y:.4f})', flush=True)
        ok = self.reset()
        print(f'reset_world returned {ok}', flush=True)
        time.sleep(1.0)
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
        print(f'POST-RESET pose=({self.pose.position.x:.4f},{self.pose.position.y:.4f})', flush=True)

        t = Twist()
        t.linear.x = 0.5
        t0 = time.time()
        while time.time() - t0 < 5.0:
            self.pub.publish(t)
            rclpy.spin_once(self, timeout_sec=0.02)
        t.linear.x = 0.0
        self.pub.publish(t)
        print(f'POST-DRIVE pose=({self.pose.position.x:.4f},{self.pose.position.y:.4f})', flush=True)
        moved = abs(self.pose.position.x - 0.0) > 0.02
        print('RESULT:', 'ROBOT_MOVES' if moved else 'ROBOT_STUCK', flush=True)


def main():
    rclpy.init()
    node = ResetDiag()
    try:
        node.run()
    except Exception as e:
        print('FAIL:', type(e).__name__, e, flush=True)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
