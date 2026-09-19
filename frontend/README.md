# FalsePay frontend

The FalsePay frontend is a Next.js application for reviewing CMS Open Payments records and guiding HCPs through a secure audit workflow.

## Run locally

Requirements: Node.js 22+ and npm.

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`. The app uses demo data when no API is available.

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
docker build -t falsepay-frontend:local .
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
- Provide only the public API URL at runtime when needed:

  ```bash
  docker run --rm --publish 127.0.0.1:3000:3000 \
    --env NEXT_PUBLIC_API_URL=https://api.example.com \
    falsepay-frontend:local
  ```

  `NEXT_PUBLIC_*` values are exposed to browser code. Do not put secrets in them. Values that must be compiled into the browser bundle should be supplied during the image build through an approved CI configuration mechanism, not committed to the repository.
- Use TLS termination, an allowlisted CORS policy on the API, rate limiting, and an authenticated secret manager in a real deployment.
- The container is intended to be read-only. If a future feature needs disk writes, mount a narrowly scoped writable volume rather than making the entire filesystem writable.

## Repository hygiene

`node_modules`, `.next`, test output, environment files, and local operating-system metadata are ignored. Keep `package-lock.json` committed so CI and container builds use the reviewed dependency graph.
