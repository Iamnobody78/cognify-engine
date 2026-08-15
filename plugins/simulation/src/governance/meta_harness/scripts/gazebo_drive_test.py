#!/usr/bin/env python3
"""Drive test: publish angular cmd_vel, watch odom yaw respond."""
import math
import os
import sys

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist


class DriveTest(Node):
    def __init__(self):
        super().__init__('drive_test')
        self.pose = None
        self.pub = self.create_publisher(Twist, '/bottlesumo/cmd_vel', 5)
        self.create_subscription(Odometry, '/bottlesumo/odom', self.on_odom, 5)

    def on_odom(self, msg):
        self.pose = msg.pose.pose

    def yaw(self):
        if self.pose is None:
            return None
        q = self.pose.orientation
        return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                          1.0 - 2.0 * (q.y * q.y + q.z * q.z))

    def run(self):
        # warm up odom
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
        y0 = self.yaw()
        print(f'initial yaw={y0:.3f} pose=({self.pose.position.x:.3f},{self.pose.position.y:.3f})', flush=True)
        t = Twist()
        t.angular.z = 1.2
        # publish turn for 3s while spinning
        import time
        t0 = time.time()
        last = y0
        while time.time() - t0 < 3.0:
            self.pub.publish(t)
            rclpy.spin_once(self, timeout_sec=0.02)
            y = self.yaw()
            if y is not None and abs(y - last) > 0.05:
                print(f'  yaw={y:.3f} d={y - y0:.3f}  pose=({self.pose.position.x:.3f},{self.pose.position.y:.3f})', flush=True)
                last = y
        y1 = self.yaw()
        print(f'final yaw={y1:.3f}  delta={y1 - y0:.3f} rad  '
              f'pose=({self.pose.position.x:.3f},{self.pose.position.y:.3f})', flush=True)
        t2 = Twist()
        self.pub.publish(t2)
        print('RESULT:', 'ROTATES' if abs(y1 - y0) > 0.3 else 'NO_MOTION', flush=True)


def main():
    rclpy.init()
    node = DriveTest()
    try:
        node.run()
    except Exception as e:
        print('FAIL:', type(e).__name__, e, flush=True)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
