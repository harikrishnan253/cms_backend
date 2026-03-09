from fastapi import Depends, HTTPException, status
from app.models import User
from app.auth import get_current_user

def require_role(role_name: str):
    def role_checker(user: User = Depends(get_current_user)):
        # Check if user has the role
        # Assuming user.roles is a list of Role objects
        user_role_names = [r.name for r in user.roles]
        if role_name not in user_role_names:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires {role_name} role"
            )
        return user
    return role_checker
