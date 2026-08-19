export {};

declare global {
  interface Window {
    __ILG_QA__: Window["__LIQUID_GLASS_QA__"];
    __LIQUID_GLASS_QA__: {
      pause(): void;
      resume(): void;
      setTime(seconds: number): void;
      setOffset(x: number, y: number): void;
      setVelocity(x: number, y: number): void;
      setQuality(level: "high" | "medium" | "low"): void;
      setDpr(value: number): void;
      setPointer(x: number, y: number): void;
      getState(): {
        ready: boolean;
        backend: string;
        quality: string;
        debug: string;
        milestone: number;
        lab?: boolean;
        glass?: string;
        scrollX: number;
        scrollY: number;
        velocityX: number;
        velocityY: number;
        dragging: boolean;
        pointerX: number;
        pointerY: number;
        pointerTargetX: number;
        pointerTargetY: number;
        rotX: number;
        rotY: number;
        camX: number;
        camY: number;
        landmarks: Array<{ nx: number; ny: number; i: number; j: number; slotIndex: number }>;
      };
      getMetrics(): {
        backend: string;
        medianFrameMs: number;
        p95FrameMs: number;
        fps: number;
      };
      getPoolState(): {
        slots: number;
        created: number;
        destroyed: number;
        remaps: number;
        cols: number;
        rows: number;
        textures?: number;
        glass?: string;
      };
      getAssetState(): {
        videos: number;
        textures: number;
        ready: boolean;
        media?: string;
        glass?: string;
        placeholderTileCount?: number;
        unreadyVisibleTileCount?: number;
      };
      setBackground?(kind: string): void;
      reset(): void;
    };
  }
}
