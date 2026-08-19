import { MeshBasicNodeMaterial, type Texture } from "three/webgpu";
import {
  Fn,
  cameraPosition,
  clamp,
  float,
  max,
  mix,
  normalize,
  normalWorld,
  positionWorld,
  pow,
  refract,
  screenUV,
  texture,
  uniform,
  uv,
  vec2,
  vec3,
} from "three/tsl";
import { GLASS } from "../config";
import type { GlassDebugMode } from "../debug/DebugMode";

export function createGlassParams() {
  return {
    ior: uniform(GLASS.ior),
    warp: uniform(GLASS.warp),
    rimPower: uniform(GLASS.rimPower),
    dispersion: uniform(GLASS.dispersion),
    fresnel: uniform(GLASS.fresnel),
    absorption: uniform(GLASS.absorption),
    blur: uniform(GLASS.blur),
  };
}

export type GlassParamSet = ReturnType<typeof createGlassParams>;

export type GlassMaterialHandle = {
  material: MeshBasicNodeMaterial;
  params: GlassParamSet;
  setMap: (map: Texture) => void;
  setMedia: (map: Texture) => void;
};

export function createGlassMaterial(
  sceneMap: Texture,
  params: GlassParamSet,
  debug: GlassDebugMode | "off" = "off",
  mediaMap?: Texture,
): GlassMaterialHandle {
  const scene = texture(sceneMap);
  const media = texture(mediaMap ?? sceneMap);
  const colorNode = Fn(() => {
    const n = normalize(normalWorld);
    const view = normalize(cameraPosition.sub(positionWorld));
    const facing = clamp(n.dot(view), 0, 1);
    const side = float(1).sub(facing);
    const rd = refract(view.mul(-1), n, float(1).div(params.ior));
    const rim = uv(1).x;
    const thick = uv(1).y;
    const warp = pow(rim, params.rimPower)
      .mul(params.warp)
      .mul(thick.mul(0.55).add(0.45))
      .add(side.mul(0.05));
    const inward = vec2(n.x.mul(-1), n.y);
    const bend = vec2(rd.x.add(inward.x), rd.y.mul(-1).add(inward.y)).mul(0.5);
    const offset = bend.mul(warp);
    const screen = screenUV.add(offset);
    const neighbor = screenUV.add(vec2(n.x, n.y.mul(-1)).mul(warp.mul(0.28)));
    const perp = vec2(offset.y.mul(-1), offset.x).mul(params.blur).mul(pow(rim, float(1.5)));
    const uvR = screen.add(offset.mul(params.dispersion).mul(pow(rim, float(0.85)).add(0.2)));
    const uvB = screen.sub(offset.mul(params.dispersion).mul(pow(rim, float(0.85)).add(0.2)));
    const world = scene.sample(screen);
    const red = scene.sample(uvR);
    const blue = scene.sample(uvB);
    const sharp = vec3(red.r, world.g, blue.b);
    const blurA = scene.sample(screen.add(perp));
    const blurB = scene.sample(screen.sub(perp));
    const foldedWorld = sharp.add(blurA.rgb).add(blurB.rgb).div(3);
    const beside = scene.sample(neighbor).rgb;
    const worldMix = mix(foldedWorld, beside, pow(rim, float(2.4)).mul(0.4).add(side.mul(0.2)));

    const disp = params.dispersion.mul(pow(rim, float(1.05)).add(0.12));
    const ownUv = uv().add(vec2(offset.x, offset.y.mul(-1)).mul(0.38));
    const ownR = media.sample(ownUv.add(offset.mul(disp)));
    const ownC = media.sample(ownUv);
    const ownB = media.sample(ownUv.sub(offset.mul(disp)));
    const own = vec3(ownR.r, ownC.g, ownB.b);
    const worldLum = clamp(worldMix.r.add(worldMix.g).add(worldMix.b).div(3).mul(1.6), 0, 1);
    const leak = mediaMap
      ? worldLum.mul(pow(rim, float(1.6)).mul(0.38).add(side.mul(0.18)))
      : float(1);
    const mediaColor = mix(own, worldMix, leak);
    const body = vec3(0.045, 0.05, 0.07);
    const absorbed = mix(mediaColor, body, rim.mul(params.absorption).mul(0.7));
    const fres = pow(float(1).sub(facing), float(2.8)).mul(params.fresnel);
    const spec = pow(max(n.y, 0), float(14)).mul(0.28).mul(float(1).sub(rim.mul(0.15)));
    const beauty = mix(absorbed, vec3(0.62, 0.7, 0.82), fres).add(vec3(spec, spec, spec));

    if (debug === "normals") return n.mul(0.5).add(0.5);
    if (debug === "thickness") return vec3(rim, thick, float(1).sub(rim));
    if (debug === "refraction") return vec3(offset.x.mul(6).add(0.5), offset.y.mul(6).add(0.5), rim);
    if (debug === "fresnel") return vec3(fres, fres, fres);
    if (debug === "dispersion") return vec3(red.r, 0, blue.b);
    if (debug === "media") return mediaMap ? ownC.rgb : scene.sample(screenUV).rgb;
    return beauty;
  })();

  const material = new MeshBasicNodeMaterial();
  material.colorNode = colorNode;
  material.transparent = false;
  material.depthWrite = true;
  material.toneMapped = debug === "off" || debug === "typography";

  return {
    material,
    params,
    setMap: (next) => {
      scene.value = next;
    },
    setMedia: (next) => {
      media.value = next;
    },
  };
}

export function setGlassParam(params: GlassParamSet, key: keyof GlassParamSet, value: number) {
  params[key].value = value;
}
