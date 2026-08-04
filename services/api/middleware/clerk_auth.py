from fastapi import Request
from fastapi.responses import JSONResponse
import jwt
import os


async def clerk_auth_middleware(request: Request, call_next):
    path = request.url.path

    # Always allow these paths without auth
    if path.startswith(("/health", "/docs", "/openapi.json", "/ws/")) or path == "/":
        return await call_next(request)

    # Allow preflight OPTIONS requests (CORS)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Demo mode: skip auth entirely when Clerk is not configured
    clerk_key = os.getenv("CLERK_SECRET_KEY", "")
    if not clerk_key:
        request.state.user_id = "demo_user"
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})

    token = auth_header.split(" ")[1]
    
    # In a real app we'd verify against Clerk's JWKS. 
    # For demo purposes, we will accept the token if it decodes, or just bypass strict validation.
    try:
        # We disable verification of signature for the demo since Clerk provides it to the Next.js app,
        # but to strictly verify in Python we'd need the PEM public key.
        decoded = jwt.decode(token, options={"verify_signature": False})
        request.state.user_id = decoded.get("sub")
    except Exception as e:
        return JSONResponse(status_code=401, content={"detail": f"Invalid token: {e}"})

    return await call_next(request)
