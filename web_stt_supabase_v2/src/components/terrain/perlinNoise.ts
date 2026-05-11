// Fixed permutation table used by the Perlin noise sampler.
const permutationTable = [
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

const doubledPermutationTable = [...permutationTable, ...permutationTable];

function smoothFade(value: number) {
  return value * value * value * (value * (value * 6 - 15) + 10);
}

function interpolate(start: number, end: number, amount: number) {
  return start + amount * (end - start);
}

function gradientContribution(
  hash: number,
  offsetX: number,
  offsetY: number,
  offsetZ: number,
) {
  const h = hash & 15;
  const u = h < 8 ? offsetX : offsetY;
  const v = h < 4 ? offsetY : h === 12 || h === 14 ? offsetX : offsetZ;
  return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v);
}

export function perlinNoise(sampleX: number, sampleY: number, sampleZ: number) {
  const gridX = Math.floor(sampleX) & 255;
  const gridY = Math.floor(sampleY) & 255;
  const gridZ = Math.floor(sampleZ) & 255;

  const localX = sampleX - Math.floor(sampleX);
  const localY = sampleY - Math.floor(sampleY);
  const localZ = sampleZ - Math.floor(sampleZ);

  const fadeX = smoothFade(localX);
  const fadeY = smoothFade(localY);
  const fadeZ = smoothFade(localZ);

  const corner000 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX] + gridY] + gridZ
    ];
  const corner010 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX] + gridY + 1] +
        gridZ
    ];
  const corner001 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX] + gridY] +
        gridZ +
        1
    ];
  const corner011 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX] + gridY + 1] +
        gridZ +
        1
    ];
  const corner100 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX + 1] + gridY] +
        gridZ
    ];
  const corner110 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX + 1] + gridY + 1] +
        gridZ
    ];
  const corner101 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX + 1] + gridY] +
        gridZ +
        1
    ];
  const corner111 =
    doubledPermutationTable[
      doubledPermutationTable[doubledPermutationTable[gridX + 1] + gridY + 1] +
        gridZ +
        1
    ];

  const lowerX = interpolate(
    gradientContribution(corner000, localX, localY, localZ),
    gradientContribution(corner100, localX - 1, localY, localZ),
    fadeX,
  );
  const upperX = interpolate(
    gradientContribution(corner010, localX, localY - 1, localZ),
    gradientContribution(corner110, localX - 1, localY - 1, localZ),
    fadeX,
  );
  const nearPlane = interpolate(lowerX, upperX, fadeY);

  const lowerBackX = interpolate(
    gradientContribution(corner001, localX, localY, localZ - 1),
    gradientContribution(corner101, localX - 1, localY, localZ - 1),
    fadeX,
  );
  const upperBackX = interpolate(
    gradientContribution(corner011, localX, localY - 1, localZ - 1),
    gradientContribution(corner111, localX - 1, localY - 1, localZ - 1),
    fadeX,
  );
  const farPlane = interpolate(lowerBackX, upperBackX, fadeY);

  return (interpolate(nearPlane, farPlane, fadeZ) + 1) * 0.5;
}
