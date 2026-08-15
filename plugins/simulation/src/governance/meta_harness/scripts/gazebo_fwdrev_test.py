#!/usr/bin/env python3
"""Verify hypothesis: reverse drive breaks gazebo_ros_diff_drive in this env."""
import os
import sys
import time

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist


class FwdRevTest(Node):
    def __init__(self):
        super().__init__('fwdrev_test')
        self.pose = None
        self.pub = self.create_publisher(Twist, '/bottlesumo/cmd_vel', 5)
        self.create_subscription(Odometry, '/bottlesumo/odom', self.on_odom, 5)

    def on_odom(self, msg):
        self.pose = msg.pose.pose

    def drive(self, vx, dur):
        t = Twist()
        t.linear.x = vx
        t0 = time.time()
        while time.time() - t0 < dur:
            self.pub.publish(t)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.02)
        t.linear.x = 0.0
        self.pub.publish(t)

    def pos(self):
        return (self.pose.position.x, self.pose.position.y)

    def run(self):
        for _ in range(30):
            rclpy.spin_once(self, timeout_sec=0.1)
        p0 = self.pos()
        print(f'start {p0}', flush=True)
        self.drive(0.5, 4.0)
        p1 = self.pos()
        print(f'after FWD 4s: {p1}  dx={p1[0]-p0[0]:.3f}', flush=True)
        self.drive(-0.5, 4.0)
        p2 = self.pos()
        print(f'after REV 4s: {p2}  dx={p2[0]-p1[0]:.3f}', flush=True)
        self.drive(0.5, 4.0)
        p3 = self.pos()
        print(f'after FWD2 4s: {p3}  dx={p3[0]-p2[0]:.3f}', flush=True)
        print(f'RESULT fwd_ok={abs(p1[0]-p0[0])>0.05} rev_ok={abs(p2[0]-p1[0])>0.05} '
              f'fwd2_ok={abs(p3[0]-p2[0])>0.05}', flush=True)


def main():
    rclpy.init()
    node = FwdRevTest()
    try:
        node.run()
    except Exception as e:
        print('FAIL:', type(e).__name__, e, flush=True)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
