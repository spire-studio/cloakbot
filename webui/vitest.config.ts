import viteConfig from './vite.config'

import { defineConfig, mergeConfig } from 'vitest/config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      css: true,
      setupFiles: ['./src/shared/test/setup.ts'],
    },
  }),
)
