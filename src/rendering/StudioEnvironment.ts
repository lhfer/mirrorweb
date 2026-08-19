import type { WebGLRenderer } from "three";
import {
  AmbientLight,
  DirectionalLight,
  HemisphereLight,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  PMREMGenerator,
  Scene,
  type WebGPURenderer,
} from "three/webgpu";

export function addStudioLights(scene: Scene) {
  scene.add(new AmbientLight(0xffffff, 0.22));
  scene.add(new HemisphereLight(0xe8eef8, 0x101018, 0.35));
  const key = new DirectionalLight(0xffffff, 1.35);
  key.position.set(-420, 720, 1100);
  scene.add(key);
  const rim = new DirectionalLight(0xf2f6ff, 0.55);
  rim.position.set(520, 480, 900);
  scene.add(rim);
  return { key, rim };
}

export function createStudioEnvironment(renderer: WebGPURenderer | WebGLRenderer) {
  const envScene = new Scene();
  const mat = new MeshBasicMaterial({ color: 0xf4f1ea });
  const bright = new MeshBasicMaterial({ color: 0xffffff });
  const geo = new PlaneGeometry(400, 180);
  const left = new Mesh(geo, bright);
  left.position.set(-160, 140, 80);
  left.rotation.y = 0.8;
  const right = new Mesh(geo, bright);
  right.position.set(160, 140, 80);
  right.rotation.y = -0.8;
  const floor = new Mesh(new PlaneGeometry(500, 500), mat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -80;
  envScene.add(left, right, floor);

  const pmrem = new PMREMGenerator(renderer as never);
  const target = pmrem.fromScene(envScene, 0.04);
  envScene.traverse((obj) => {
    if (obj instanceof Mesh) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((item) => item.dispose());
      else material.dispose();
    }
  });
  pmrem.dispose();
  return target.texture;
}
