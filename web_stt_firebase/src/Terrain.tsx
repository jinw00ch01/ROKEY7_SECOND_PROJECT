import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { RobotMode } from "./types";

type Props = {
  mode: RobotMode;
};

const TERRAIN_SIZE = 12;
const SEGMENTS = 56;
const VERTICES_PER_SIDE = SEGMENTS + 1;
const CURVE_STEPS = 5;
const MAX_EDGES = SEGMENTS * SEGMENTS * 3;
const LINE_VERTEX_COUNT = MAX_EDGES * CURVE_STEPS * 2;

const permutation = [
  151, 160, 137, 91, 90, 15, 131, 13, 201, 95, 96, 53, 194, 233, 7, 225, 140,
  36, 103, 30, 69, 142, 8, 99, 37, 240, 21, 10, 23, 190, 6, 148, 247, 120,
  234, 75, 0, 26, 197, 62, 94, 252, 219, 203, 117, 35, 11, 32, 57, 177, 33,
  88, 237, 149, 56, 87, 174, 20, 125, 136, 171, 168, 68, 175, 74, 165, 71,
  134, 139, 48, 27, 166, 77, 146, 158, 231, 83, 111, 229, 122, 60, 211, 133,
  230, 220, 105, 92, 41, 55, 46, 245, 40, 244, 102, 143, 54, 65, 25, 63, 161,
  1, 216, 80, 73, 209, 76, 132, 187, 208, 89, 18, 169, 200, 196, 135, 130,
  116, 188, 159, 86, 164, 100, 109, 198, 173, 186, 3, 64, 52, 217, 226, 250,
  124, 123, 5, 202, 38, 147, 118, 126, 255, 82, 85, 212, 207, 206, 59, 227,
  47, 16, 58, 17, 182, 189, 28, 42, 223, 183, 170, 213, 119, 248, 152, 2, 44,
  154, 163, 70, 221, 153, 101, 155, 167, 43, 172, 9, 129, 22, 39, 253, 19, 98,
  108, 110, 79, 113, 224, 232, 178, 185, 112, 104, 218, 246, 97, 228, 251, 34,
  242, 193, 238, 210, 144, 12, 191, 179, 162, 241, 81, 51, 145, 235, 249, 14,
  239, 107, 49, 192, 214, 31, 181, 199, 106, 157, 184, 84, 204, 176, 115, 121,
  50, 45, 127, 4, 150, 254, 138, 236, 205, 93, 222, 114, 67, 29, 24, 72, 243,
  141, 128, 195, 78, 66, 215, 61, 156, 180,
];

const p = [...permutation, ...permutation];

function fade(t: number) {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

function lerp(a: number, b: number, t: number) {
  return a + t * (b - a);
}

function grad(hash: number, x: number, y: number, z: number) {
  const h = hash & 15;
  const u = h < 8 ? x : y;
  const v = h < 4 ? y : h === 12 || h === 14 ? x : z;
  return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v);
}

function noise(x: number, y: number, z: number) {
  const xi = Math.floor(x) & 255;
  const yi = Math.floor(y) & 255;
  const zi = Math.floor(z) & 255;

  const xf = x - Math.floor(x);
  const yf = y - Math.floor(y);
  const zf = z - Math.floor(z);

  const u = fade(xf);
  const v = fade(yf);
  const w = fade(zf);

  const aaa = p[p[p[xi] + yi] + zi];
  const aba = p[p[p[xi] + yi + 1] + zi];
  const aab = p[p[p[xi] + yi] + zi + 1];
  const abb = p[p[p[xi] + yi + 1] + zi + 1];
  const baa = p[p[p[xi + 1] + yi] + zi];
  const bba = p[p[p[xi + 1] + yi + 1] + zi];
  const bab = p[p[p[xi + 1] + yi] + zi + 1];
  const bbb = p[p[p[xi + 1] + yi + 1] + zi + 1];

  const x1 = lerp(grad(aaa, xf, yf, zf), grad(baa, xf - 1, yf, zf), u);
  const x2 = lerp(
    grad(aba, xf, yf - 1, zf),
    grad(bba, xf - 1, yf - 1, zf),
    u,
  );
  const y1 = lerp(x1, x2, v);

  const x3 = lerp(
    grad(aab, xf, yf, zf - 1),
    grad(bab, xf - 1, yf, zf - 1),
    u,
  );
  const x4 = lerp(
    grad(abb, xf, yf - 1, zf - 1),
    grad(bbb, xf - 1, yf - 1, zf - 1),
    u,
  );
  const y2 = lerp(x3, x4, v);

  return (lerp(y1, y2, w) + 1) * 0.5;
}

function modeIntensity(mode: RobotMode) {
  if (mode === "wake_detected" || mode === "listening") return 1.25;
  if (mode === "processing") return 1.55;
  return 0.75;
}

function vertexIndex(x: number, y: number) {
  return y * VERTICES_PER_SIDE + x;
}

function getVertex(
  position: THREE.BufferAttribute,
  x: number,
  y: number,
  target: THREE.Vector3,
) {
  const i = vertexIndex(x, y);
  return target.set(position.getX(i), position.getY(i), position.getZ(i));
}

export function Terrain({ mode }: Props) {
  const meshRef = useRef<THREE.Mesh>(null);
  const linesRef = useRef<THREE.LineSegments>(null);
  const reusable = useMemo(
    () => ({
      a: new THREE.Vector3(),
      b: new THREE.Vector3(),
      c: new THREE.Vector3(),
      mid: new THREE.Vector3(),
      dir: new THREE.Vector3(),
      normal: new THREE.Vector3(),
      c1: new THREE.Vector3(),
      c2: new THREE.Vector3(),
      p0: new THREE.Vector3(),
      p1: new THREE.Vector3(),
      color: new THREE.Color(),
    }),
    [],
  );

  const lineGeometry = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(LINE_VERTEX_COUNT * 3);
    const colors = new Float32Array(LINE_VERTEX_COUNT * 3);
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.setDrawRange(0, LINE_VERTEX_COUNT);
    return geometry;
  }, []);

  useFrame(({ clock }) => {
    if (!meshRef.current || !linesRef.current) return;

    const elapsed = clock.getElapsedTime();
    const flying = elapsed * 0.42;
    const heatTime = elapsed * 0.85;
    const intensity = modeIntensity(mode);
    const geometry = meshRef.current.geometry as THREE.PlaneGeometry;
    const position = geometry.attributes.position as THREE.BufferAttribute;

    for (let y = 0; y < VERTICES_PER_SIDE; y++) {
      for (let x = 0; x < VERTICES_PER_SIDE; x++) {
        const i = vertexIndex(x, y);
        const worldX = position.getX(i);
        const worldY = position.getY(i);
        const base = noise(x * 0.1, y * 0.1 + flying, 0);
        const detail = noise(x * 0.24, y * 0.24 + flying * 1.35, 8.5);
        const height = ((base * 0.72 + detail * 0.28) * 2 - 1) * intensity;

        position.setXYZ(i, worldX, worldY, height);
      }
    }

    position.needsUpdate = true;
    geometry.computeVertexNormals();

    const linePosition = lineGeometry.attributes.position as THREE.BufferAttribute;
    const lineColor = lineGeometry.attributes.color as THREE.BufferAttribute;
    let lineVertex = 0;

    const writePoint = (point: THREE.Vector3, color: THREE.Color) => {
      linePosition.setXYZ(lineVertex, point.x, point.y, point.z + 0.03);
      lineColor.setXYZ(lineVertex, color.r, color.g, color.b);
      lineVertex += 1;
    };

    const writeFlameEdge = (from: THREE.Vector3, to: THREE.Vector3) => {
      const { mid, dir, normal, c1, c2, p0, p1, color } = reusable;

      dir.subVectors(to, from);
      mid.addVectors(from, to).multiplyScalar(0.5);
      normal.set(-dir.y, dir.x, 0).normalize();

      const heat = noise(mid.x * 0.82 + 20, mid.y * 0.82 + 20, heatTime);
      const curl = THREE.MathUtils.lerp(-0.15, 0.45, heat) * intensity;
      const hue = THREE.MathUtils.lerp(0.03, 0.15, heat);
      const brightness = THREE.MathUtils.clamp(
        THREE.MathUtils.lerp(0.62, 1, heat) *
          THREE.MathUtils.mapLinear(
            mid.y,
            -TERRAIN_SIZE / 2,
            TERRAIN_SIZE / 2,
            1.25,
            0.42,
          ),
        0.28,
        1,
      );

      c1.copy(mid).addScaledVector(normal, curl).setZ(mid.z + curl);
      c2.copy(mid).addScaledVector(normal, -curl).setZ(mid.z + curl);
      color.setHSL(hue, 1, brightness * 0.5);

      p0.copy(from);
      for (let step = 1; step <= CURVE_STEPS; step++) {
        const t = step / CURVE_STEPS;
        p1.copy(from)
          .multiplyScalar((1 - t) ** 3)
          .addScaledVector(c1, 3 * (1 - t) ** 2 * t)
          .addScaledVector(c2, 3 * (1 - t) * t * t)
          .addScaledVector(to, t ** 3);

        writePoint(p0, color);
        writePoint(p1, color);
        p0.copy(p1);
      }
    };

    for (let y = 0; y < SEGMENTS; y++) {
      for (let x = 0; x < SEGMENTS; x++) {
        const { a, b, c } = reusable;
        getVertex(position, x, y, a);
        getVertex(position, x + 1, y, b);
        getVertex(position, x, y + 1, c);

        writeFlameEdge(a, b);
        writeFlameEdge(a, c);
        writeFlameEdge(b, c);
      }
    }

    linePosition.needsUpdate = true;
    lineColor.needsUpdate = true;
    lineGeometry.setDrawRange(0, lineVertex);
  });

  return (
    <group rotation={[-Math.PI / 3, 0, 0]} position={[0, -0.4, 0]}>
      <mesh ref={meshRef}>
        <planeGeometry args={[TERRAIN_SIZE, TERRAIN_SIZE, SEGMENTS, SEGMENTS]} />
        <meshStandardMaterial
          color="#150500"
          emissive="#2c0900"
          metalness={0}
          roughness={0.85}
          transparent
          opacity={0.32}
          side={THREE.DoubleSide}
        />
      </mesh>
      <lineSegments ref={linesRef} geometry={lineGeometry}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.88}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>
    </group>
  );
}
