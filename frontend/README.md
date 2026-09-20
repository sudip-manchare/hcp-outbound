# FalsePay frontend

The FalsePay frontend is a Next.js application for reviewing CMS Open Payments records and guiding HCPs through a secure audit workflow.

## Run locally

Requirements: Node.js 22+ and npm.

```bash
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. The app renders only records returned by the API;
if the API is unavailable, it shows an error or empty state rather than fallback
data.

Before committing or releasing, run:

```bash
npm run type-check
npm run test
npm run build
```

## Production container

The included multi-stage `Dockerfile` builds Next.js standalone output, copies only runtime assets and traced dependencies into the final image, and runs the server as an unprivileged `nextjs` user.

Build from this directory so the `.dockerignore` excludes local dependencies, build output, test artifacts, and environment files:

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  -t falsepay-frontend:local .
```

Run the container bound to loopback only for local testing:

```bash
docker run --rm \
  --name falsepay-frontend \
  --publish 127.0.0.1:3000:3000 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  falsepay-frontend:local
```

Then open `http://localhost:3000`.

## Configuration and security

- Never bake credentials or `.env` files into an image. The Docker build context excludes them.
- Set the public backend URL **at build time**:

  ```bash
  docker build --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
    -t falsepay-frontend:production .
  ```

  Use the backend origin without `/api` or a trailing slash. The API client in
  `src/lib/api.ts` already reads `NEXT_PUBLIC_API_URL` and appends endpoint paths.
  This is a public URL, not an API key. Next.js compiles it into browser JavaScript;
  changing it requires rebuilding the image. `docker run --env` cannot change it.
  See the [Next.js environment variable documentation](https://nextjs.org/docs/pages/guides/environment-variables).
  Set the backend's `CORS_ORIGINS` to a JSON array containing the deployed frontend
  origin, for example `["https://app.example.com"]`.
- Use TLS termination, an allowlisted CORS policy on the API, rate limiting, and an authenticated secret manager in a real deployment.
- The container is intended to be read-only. If a future feature needs disk writes, mount a narrowly scoped writable volume rather than making the entire filesystem writable.

## Repository hygiene

`node_modules`, `.next`, test output, environment files, and local operating-system metadata are ignored. Keep `package-lock.json` committed so CI and container builds use the reviewed dependency graph.
