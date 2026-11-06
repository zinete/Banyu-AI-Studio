import * as THREE from 'three';
import type { Action } from './types';

// Programmatic 3D interpretation, not an official character model.
export type BearRig = {
  root: THREE.Group;
  head: THREE.Group;
  leftArm: THREE.Group;
  rightArm: THREE.Group;
  eyes: THREE.Group[];
  happyEyes: THREE.Group;
  mouth: THREE.Mesh;
  tongue: THREE.Mesh;
  closedMouth: THREE.Mesh;
};
const ink = '#492c26';

export function buildBear(kind: 'yier' | 'bubu'): BearRig {
  const white = kind === 'yier';
  const root = new THREE.Group();
  root.name = kind;
  const fur = new THREE.MeshStandardMaterial({ color: white ? '#fffaf5' : '#c38b6c', roughness: 1, metalness: 0 });
  const dark = new THREE.MeshBasicMaterial({ color: ink });
  const outline = new THREE.MeshBasicMaterial({ color: ink, side: THREE.BackSide });
  const cheekMaterial = new THREE.MeshBasicMaterial({ color: white ? '#f4adb4' : '#efc081' });
  const pink = new THREE.MeshBasicMaterial({ color: '#ed929f' });
  const sphere = new THREE.SphereGeometry(1, 28, 20);

  function blob(parent: THREE.Object3D, material: THREE.Material,
    position: [number, number, number], scale: [number, number, number], edged = true) {
    const mesh = new THREE.Mesh(sphere, material);
    mesh.position.set(...position);
    mesh.scale.set(...scale);
    if (edged) {
      const rim = new THREE.Mesh(sphere, outline);
      rim.scale.setScalar(1.024);
      mesh.add(rim);
    }
    parent.add(mesh);
    return mesh;
  }
  function stroke(parent: THREE.Object3D, points: [number, number, number][], thickness = .011) {
    const curve = new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p)));
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, thickness, 7, false), dark);
    parent.add(mesh);
    return mesh;
  }

  // Short limbs and oversized rounded-square heads keep the sticker proportions.
  blob(root, fur, [0, .67, -.025], [.435, .52, .325]);
  blob(root, fur, [-.245, .17, .085], [.19, .135, .25]);
  blob(root, fur, [.245, .17, .085], [.19, .135, .25]);
  blob(root, fur, [0, .52, -.36], [.13, .13, .13]);
  const arms = [-1, 1].map(side => {
    const pivot = new THREE.Group();
    pivot.position.set(side * .395, .94, .015);
    blob(pivot, fur, [0, -.175, .035], [.14, .255, .155]);
    root.add(pivot);
    return pivot;
  });

  const head = new THREE.Group();
  head.position.set(0, 1.455, .025);
  root.add(head);
  for (const side of [-1, 1]) {
    blob(head, white ? dark : fur, [side * .48, .48, -.015], [.19, .20, .13]);
    if (!white) blob(head, dark, [side * .48, .49, .106], [.105, .112, .025], false);
  }
  const headGeometry = new THREE.SphereGeometry(1, 48, 32);
  const vertices = headGeometry.getAttribute('position');
  const soften = (n: number) => Math.sign(n) * Math.pow(Math.abs(n), .9);
  for (let i = 0; i < vertices.count; i++) {
    vertices.setXYZ(i, soften(vertices.getX(i)) * .66,
      soften(vertices.getY(i)) * .565, soften(vertices.getZ(i)) * .41);
  }
  headGeometry.computeVertexNormals();
  const headMesh = new THREE.Mesh(headGeometry, fur);
  const headOutline = new THREE.Mesh(headGeometry, outline);
  headOutline.scale.set(1.018, 1.022, 1.025);
  headMesh.add(headOutline);
  head.add(headMesh);
  const eyes = [-1, 1].map(side => {
    const eye = new THREE.Group();
    eye.position.set(side * .245, -.11, .424);
    blob(eye, dark, [0, 0, 0], [.046, .055, .013], false);
    head.add(eye);
    return eye;
  });
  const happyEyes = new THREE.Group();
  for (const side of [-1, 1]) {
    const x = side * .245;
    stroke(happyEyes, [[x - .055, -.12, .437], [x, -.086, .443], [x + .055, -.12, .437]], .010);
  }
  happyEyes.visible = false;
  head.add(happyEyes);
  // Project cheek decals onto the curved face so their edges never clip into the head.
  const exponent = 2 / .9;
  const surface = (x: number, y: number) => .41 * Math.pow(Math.max(.01,
    1 - Math.pow(Math.abs(x) / .66, exponent) - Math.pow(Math.abs(y) / .565, exponent)), 1 / exponent);
  for (const side of [-1, 1]) {
    const cx = side * .437, cy = -.255;
    const positions: number[] = [];
    const indices: number[] = [];
    for (let ring = 0; ring <= 8; ring++) {
      for (let i = 0; i <= 40; i++) {
        const angle = i / 40 * Math.PI * 2, radius = ring / 8;
        const x = cx + Math.cos(angle) * .122 * radius, y = cy + Math.sin(angle) * .090 * radius;
        positions.push(x, y, surface(x, y) + .012);
        if (ring < 8 && i < 40) {
          const a = ring * 41 + i, b = a + 41;
          indices.push(a, b, a + 1, a + 1, b, b + 1);
        }
      }
    }
    const cheekGeometry = new THREE.BufferGeometry();
    cheekGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    cheekGeometry.setIndex(indices);
    head.add(new THREE.Mesh(cheekGeometry, cheekMaterial));
  }
  const closedMouth = stroke(head, [[-.067, -.168, .433], [-.047, -.204, .438],
    [0, -.188, .442], [.047, -.204, .438], [.067, -.168, .433]], .010);
  const mouth = blob(head, dark, [0, -.230, .438], [.057, .008, .014], false);
  const tongue = blob(head, pink, [0, -.25, .454], [.032, .010, .008], false);
  mouth.visible = tongue.visible = false;
  if (!white) stroke(head, [[-.10, .558, .06], [-.075, .611, .07], [-.022, .573, .07]], .012);
  return { root, head, leftArm: arms[0], rightArm: arms[1], eyes, happyEyes, mouth, tongue, closedMouth };
}

export function animateBear(rig: BearRig, kind: 'yier' | 'bubu', time: number,
  level: number, action: Action, paused: boolean, reducedMotion: boolean) {
  const white = kind === 'yier';
  const active = !paused;
  const moving = active && !reducedMotion;
  const phase = white ? 0 : .7;
  const blinkPhase = (time + phase) % 4.1;
  const blink = moving && blinkPhase > 3.9 ? Math.sin((blinkPhase - 3.9) / .2 * Math.PI) : 0;
  const happy = active && action === 'smile';
  rig.head.rotation.set(
    moving && action === 'nod' ? Math.sin(time * 4 + phase) * .10 : 0,
    moving ? Math.sin(time * .65 + phase) * .035 : 0,
    active && action === 'confused' ? (white ? -.14 : .12) : (white ? -.025 : .025),
  );
  rig.root.position.y = moving ? Math.sin(time * 2 + phase) * .012 : 0;
  rig.leftArm.rotation.z = white && moving && action === 'wave' ? -2.1 + Math.sin(time * 6) * .24 : -.18;
  rig.rightArm.rotation.z = !white && moving && action === 'wave' ? 2.1 + Math.sin(time * 6 + .3) * .24 : .18;
  rig.happyEyes.visible = happy;
  rig.eyes.forEach(eye => { eye.visible = !happy; eye.scale.y = Math.max(.08, 1 - blink); });
  const opening = white && active ? Math.max(0, Math.min(level, 1)) : 0;
  rig.mouth.visible = rig.tongue.visible = opening > .045;
  rig.closedMouth.visible = opening < .18;
  rig.mouth.scale.y = .012 + opening * .073;
  rig.tongue.position.y = -.232 - opening * .045;
  rig.tongue.scale.y = .007 + opening * .009;
  rig.root.userData.mouthLevel = opening;
}
