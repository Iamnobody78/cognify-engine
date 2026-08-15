#!/usr/bin/env python3
"""Probe /bottlesumo/odom + edge sensors, print pose + edge_min."""
import os
import sys

for _p in ('/opt/ros/humble/lib/python3.10/site-packages',
           '/opt/ros/humble/local/lib/python3.10/dist-packages'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ['LD_LIBRARY_PATH'] = '/opt/ros/humble/lib:' + os.environ.get('LD_LIBRARY_PATH', '')
os.environ['RMW_IMPLEMENTATION'] = 'rmw_fastrtps_cpp'
os.environ['FASTRTPS_DEFAULT_PROFILES_FILE'] = '/tmp/fastdds_udp.xml'

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Range

DOHYO_R = 0.385


class Probe(Node):
    def __init__(self):
        super().__init__('odom_probe')
        self.pose = None
        self.edges = {}
        self.create_subscription(Odometry, '/bottlesumo/odom', self.on_odom, 5)
        for name in ('front', 'back', 'left', 'right'):
            self.create_subscription(Range, f'/bottlesumo/edge_{name}', self.on_edge(name), 5)
        self.create_timer(0.05, self.on_tick)

    def on_odom(self, msg):
        self.pose = msg.pose.pose

    def on_edge(self, name):
        def cb(msg):
            self.edges[name] = msg.range
        return cb

    def on_tick(self):
        if self.pose is not None:
            x, y = self.pose.position.x, self.pose.position.y
            r = (x * x + y * y) ** 0.5
            em = DOHYO_R - r
            print(f'pose=({x:.3f},{y:.3f}) r={r:.3f} edge_min={em:.3f} '
                  f'edges={ {k: round(v,3) for k,v in self.edges.items()} }', flush=True)


def main():
    rclpy.init()
    node = Probe()
    try:
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=2.0)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
