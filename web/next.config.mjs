/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL ?? "http://localhost:8000";

// Política de segurança de conteúdo das páginas do Next (a API já manda os próprios cabeçalhos).
// - script-src com 'unsafe-inline': o Next injeta scripts inline de hidratação e há o script do tema; trocar
//   por nonce exige middleware e renderização dinâmica — anotado em docs/security-audit.md.
// - frame-src/object-src com blob:: o leitor mostra o PDF do próprio usuário num iframe (URL blob:), e o
//   documento blob herda esta política; sem blob:, o visualizador de PDF do navegador seria bloqueado.
// - fontes servidas pelo próprio site (next/font): nenhum pedido a fonts.googleapis.com.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "production" ? "" : " 'unsafe-eval'"),
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "frame-src 'self' blob:",
  "object-src 'self' blob:",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig = {
  poweredByHeader: false,
  async rewrites() {
    // O navegador chama /api/... no próprio Next; o Next repassa ao FastAPI.
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;
