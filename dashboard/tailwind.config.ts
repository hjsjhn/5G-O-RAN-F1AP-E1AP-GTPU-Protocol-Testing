import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/client/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        shell: "#08111d",
        panel: "#101c2d",
        line: "#22334a",
        accent: "#3ecf8e",
        warn: "#f4b740",
        danger: "#ef6b73",
        ink: "#e8f1fb",
        muted: "#8ea3bc"
      },
      boxShadow: {
        panel: "0 20px 60px rgba(3, 12, 22, 0.28)"
      },
      fontFamily: {
        sans: [
          "\"Noto Sans SC\"",
          "\"PingFang SC\"",
          "\"Hiragino Sans GB\"",
          "\"Microsoft YaHei\"",
          "sans-serif"
        ],
        mono: [
          "\"SFMono-Regular\"",
          "\"JetBrains Mono\"",
          "\"Menlo\"",
          "monospace"
        ]
      }
    }
  },
  plugins: []
} satisfies Config;
