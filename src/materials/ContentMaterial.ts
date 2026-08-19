import { MeshBasicMaterial, type Texture } from "three/webgpu";

export function createContentMaterial(map: Texture) {
  return new MeshBasicMaterial({
    map,
    toneMapped: false,
  });
}
