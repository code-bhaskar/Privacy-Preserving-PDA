from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.controllers.user_controller import user_controller
from app.core.auth import get_current_user, oauth2_scheme, revoke_token
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.consent import ConsentRead, ConsentSet
from app.schemas.user import Token, UserCreate, UserLogin, UserRead

router = APIRouter(tags=["users"])


# Documented request bodies for POST /login. The endpoint accepts two formats,
# which cannot be declared in one FastAPI signature (Form and Body parameters
# cannot be mixed), so the OpenAPI requestBody is provided explicitly:
#   - application/json                  : {"email", "password"}
#       (regular API clients — original contract, unchanged)
#   - application/x-www-form-urlencoded : "username"/"email" + "password"
#       (standard OAuth2 *password grant* — what Swagger UI's "Authorize"
#        dialog POSTs to the token URL)
LOGIN_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": UserLogin.model_json_schema(),
        },
        "application/x-www-form-urlencoded": {
            "schema": {
                "type": "object",
                "title": "OAuth2 password grant",
                "properties": {
                    "username": {
                        "type": "string",
                        "format": "email",
                        "title": "Username",
                        "description": "The user's email address (OAuth2 'username' field).",
                    },
                    "password": {"type": "string", "title": "Password"},
                },
                "required": ["username", "password"],
            },
        },
    },
}


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    return user_controller.create(db, payload)


@router.post(
    "/login",
    response_model=Token,
    openapi_extra={"requestBody": LOGIN_REQUEST_BODY},
)
async def login(request: Request, db: Session = Depends(get_db)):
    """Authenticate and return a JWT.

    Accepts both:
    - ``application/json`` with ``{"email", "password"}`` (API clients), and
    - the standard OAuth2 *password grant* form (``username``/``email`` +
      ``password``) that Swagger UI's "Authorize" dialog POSTs to the token
      URL.  Without the form branch the OAuth2 flow always failed with 422,
      because the dialog sends form data, not JSON.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    email: str | None = None
    password: str | None = None

    if content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
        form = await request.form()
        # OAuth2's credential field is "username"; this app logs in by email,
        # so accept "email" too for clients that name the field directly.
        email = form.get("email") or form.get("username")
        password = form.get("password")
    elif content_type == "application/json":
        try:
            raw = await request.json()
        except (ValueError, UnicodeDecodeError):
            raw = None
        if isinstance(raw, dict):
            email = raw.get("email")
            password = raw.get("password")

    try:
        payload = UserLogin(email=email, password=password)
    except PydanticValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Login requires a valid 'email' and 'password'",
        )

    return user_controller.login(db, payload)


@router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
):
    """Revoke active JWT bearer token."""
    revoke_token(token)
    return {"message": "Successfully logged out"}


@router.get("/users/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Get the authenticated user by ID",
    description=(
        "Pass the user ID as a path parameter, for example "
        "`GET /api/v1/users/42`. The ID must belong to the authenticated "
        "user; requests for another user's ID return 404 to prevent user "
        "enumeration. Use `GET /api/v1/users/me` when the ID is not known."
    ),
)
def get_user(
    user_id: int = Path(
        ...,
        title="User ID",
        description="The ID returned by registration or GET /api/v1/users/me.",
        ge=1,
        examples=[1],
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise NotFoundError("User not found")
    return user_controller.get(db, user_id)


@router.post("/consent", response_model=ConsentRead)
def set_consent(
    payload: ConsentSet,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_controller.set_consent(db, current_user.id, payload)


@router.get("/consent", response_model=list[ConsentRead])
def get_my_consent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_controller.get_consent(db, current_user.id)


@router.get("/consent/{user_id}", response_model=list[ConsentRead])
def get_consent(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise NotFoundError("User not found")
    return user_controller.get_consent(db, current_user.id)
