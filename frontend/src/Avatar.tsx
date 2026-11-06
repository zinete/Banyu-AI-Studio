import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { animateBear, buildBear } from './bears';
import type { Action } from './types';

type Props = {
  mouth: React.RefObject<number>;
  action: Action;
  paused: boolean;
  onReady: (ok: boolean) => void;
  onFps: (value: number) => void;
};

export function Avatar({ mouth, action, paused, onReady, onFps }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const state = useRef({ action, paused });
  const callbacks = useRef({ onReady, onFps });
  state.current = { action, paused };
  callbacks.current = { onReady, onFps };
  const [error, setError] = useState('');

  useEffect(() => {
    const container = host.current!;
    let frame = 0;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true }); }
    catch {
      setError('无法初始化 3D，请检查浏览器硬件加速');
      callbacks.current.onReady(false);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    renderer.domElement.setAttribute('aria-label', '一二和布布的 3D 卡通形象');
    renderer.domElement.dataset.avatar = 'yier-bubu';
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#201e1d');
    const camera = new THREE.OrthographicCamera(-2, 2, 1.5, -1.5, .1, 30);
    camera.position.set(0, 1.62, 7);
    camera.lookAt(0, 1.10, 0);
    scene.add(new THREE.HemisphereLight('#fff5e9', '#a4a2a0', 2));
    const key = new THREE.DirectionalLight('#fff2df', 2.8);
    key.position.set(-3, 5, 5);
    scene.add(key);
    const fill = new THREE.DirectionalLight('#e3ecfa', .8);
    fill.position.set(3, 2, 2);
    scene.add(fill);
    const yier = buildBear('yier');
    const bubu = buildBear('bubu');
    yier.root.position.x = -.76;
    bubu.root.position.x = .76;
    yier.root.rotation.y = .055;
    bubu.root.rotation.y = -.055;
    scene.add(yier.root, bubu.root);
    const platform = new THREE.Mesh(new THREE.CylinderGeometry(1.7, 1.75, .07, 64),
      new THREE.MeshStandardMaterial({ color: '#3a3633', roughness: 1 }));
    platform.scale.z = .48;
    platform.position.y = -.005;
    scene.add(platform);
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frames = 0;
    let previousSample = performance.now();
    const started = performance.now();
    const resize = new ResizeObserver(() => {
      const width = Math.max(container.clientWidth, 1);
      const height = Math.max(container.clientHeight, 1);
      const aspect = width / height;
      const visibleHeight = Math.max(2.85, 3.35 / aspect);
      camera.left = -visibleHeight * aspect / 2;
      camera.right = visibleHeight * aspect / 2;
      camera.top = visibleHeight / 2;
      camera.bottom = -visibleHeight / 2;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    });
    resize.observe(container);
    function render() {
      const time = (performance.now() - started) / 1000;
      const { action: currentAction, paused: currentPaused } = state.current;
      animateBear(yier, 'yier', time, mouth.current, currentAction, currentPaused, reducedMotion.matches);
      animateBear(bubu, 'bubu', time, 0, currentAction, currentPaused, reducedMotion.matches);
      renderer.domElement.dataset.mouth = String(yier.root.userData.mouthLevel);
      renderer.domElement.dataset.action = currentPaused ? 'idle' : currentAction;
      renderer.render(scene, camera);
      frames++;
      const now = performance.now();
      if (now - previousSample >= 5000) {
        callbacks.current.onFps(frames * 1000 / (now - previousSample));
        frames = 0;
        previousSample = now;
      }
      frame = requestAnimationFrame(render);
    }
    render();
    callbacks.current.onReady(true);
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      const geometries = new Set<THREE.BufferGeometry>();
      const materials = new Set<THREE.Material>();
      scene.traverse(node => {
        if (node instanceof THREE.Mesh) {
          geometries.add(node.geometry);
          (Array.isArray(node.material) ? node.material : [node.material]).forEach(m => materials.add(m));
        }
      });
      geometries.forEach(geometry => geometry.dispose());
      materials.forEach(material => material.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [mouth]);
  return <div className="avatar" ref={host}>
    {error && <div className="avatar-error" role="alert">{error}</div>}
  </div>;
}
