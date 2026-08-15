#!/bin/bash
# Dump robot dimensions from URDF
echo "=== chassis / body geometry ==="
grep -A10 '<link name="chassis_link"' /tmp/bottlesumo.urdf | grep -E '<box|<cylinder|<sphere|size|radius' | head -6
echo "=== any box/size in links ==="
grep -oE '<box size="[^"]*"|<cylinder radius="[^"]*"[^>]*length="[^"]*"|<sphere radius="[^"]*"' /tmp/bottlesumo.urdf | head -12
echo "=== wheel joints ==="
grep -oE 'name="[a-z_]*wheel[a-z_]*_joint"' /tmp/bottlesumo.urdf | head -4
