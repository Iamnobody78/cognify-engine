"""TASK-007 smoke test: launch Gazebo stack + GetModelState probe.

Verifies the critical risk items before the 20-episode harvest:
  1. bottlesumo_simple.launch.py boots (RSP -> gzserver -> spawn_entity)
  2. /gazebo/get_model_state service is available (pose ground-truth)
  3. edge_min geometric definition works (0.385 - r)

Run inside WSL:  python3 /mnt/c/.../gazebo_smoke.py
"""
import os
import subprocess
import sys
import time

# Ensure ROS2 python packages are importable (rclpy, gazebo_msgs...)
for _p in ('/opt/ros/humble/lib/python3.10/site-packages',
           '/opt/ros/humble/local/lib/python3.10/dist-packages'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ['PYTHONPATH'] = ':'.join([
    '/opt/ros/humble/lib/python3.10/site-packages',
    '/opt/ros/humble/local/lib/python3.10/dist-packages',
    os.environ.get('PYTHONPATH', '')])
os.environ['LD_LIBRARY_PATH'] = (
    '/opt/ros/humble/lib:' + os.environ.get('LD_LIBRARY_PATH', ''))
os.environ['AMENT_PREFIX_PATH'] = (
    '/opt/ros/humble:' + os.environ.get('AMENT_PREFIX_PATH', ''))

WS = '/home/ivy/bottlesumo_ws'
DOHYO_R = 0.385


def cleanup(procs):
    for p in procs:
        if p and p.poll() is None:
            p.terminate()
    time.sleep(1)
    for p in procs:
        if p and p.poll() is None:
            p.kill()
    subprocess.run(['pkill', '-f', 'gzserver'], capture_output=True)
    subprocess.run(['pkill', '-f', 'robot_state_publisher'], capture_output=True)
    subprocess.run(['pkill', '-f', 'Xvfb'], capture_output=True)


def main():
    procs = []
    # 1. Xvfb headless display
    subprocess.run(['pkill', '-f', 'Xvfb'], capture_output=True)
    time.sleep(0.3)
    xvfb = subprocess.Popen(
        ['Xvfb', ':99', '-screen', '0', '1280x720x24', '-ac'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(xvfb)
    os.environ['DISPLAY'] = ':99'
    time.sleep(0.5)
    print('[SMOKE] Xvfb up on :99', flush=True)

    # 2. Launch ROS2 + Gazebo stack
    cmd = (f'source /opt/ros/humble/setup.bash && source {WS}/install/setup.bash && '
           f'ros2 launch bottlesumo_description bottlesumo_simple.launch.py')
    gazebo = subprocess.Popen(['bash', '-lc', cmd],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(gazebo)
    print('[SMOKE] Launching stack, waiting 20s...', flush=True)
    time.sleep(20)

    # 3. Probe GetModelState
    import rclpy
    from gazebo_msgs.srv import GetModelState
    rclpy.init()
    node = rclpy.create_node('smoke_probe')
    cli = node.create_client(GetModelState, '/gazebo/get_model_state')
    ok = False
    for i in range(15):
        if cli.wait_for_service(timeout_sec=1.0):
            ok = True
            break
        print(f'[SMOKE] waiting get_model_state... {i}', flush=True)
    if not ok:
        err = gazebo.stderr.read(500).decode(errors='replace') if gazebo.stderr else ''
        print(f'[SMOKE] FAIL: service unavailable. stderr tail: {err[-400:]}', flush=True)
        cleanup(procs)
        return 1

    req = GetModelState.Request()
    req.model_name = 'bottlesumo'
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=10)
    resp = fut.result()
    if resp is None or not resp.success:
        print('[SMOKE] FAIL: GetModelState returned error', flush=True)
        cleanup(procs)
        return 1
    x, y = resp.pose.position.x, resp.pose.position.y
    r = (x * x + y * y) ** 0.5
    edge_min = DOHYO_R - r
    print(f'[SMOKE] PASS: bottlesumo pose x={x:.4f} y={y:.4f} z={resp.pose.position.z:.4f}', flush=True)
    print(f'[SMOKE] PASS: r={r:.4f}  edge_min={edge_min:.4f}  (dohyo R={DOHYO_R})', flush=True)
    print(f'[SMOKE] trigger check: edge_min<0.20 -> {"TRIGGER" if edge_min < 0.20 else "SAFE"}', flush=True)

    # 4. Quick sensor sanity: any topic traffic?
    node.destroy_node()
    rclpy.shutdown()

    cleanup(procs)
    print('[SMOKE] ALL PASS, cleaned up', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
