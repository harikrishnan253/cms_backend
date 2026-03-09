from app.database import SessionLocal
from app.models import Role, User
from app.auth import pwd_context

def reset_admin():
    db = SessionLocal()
    try:
        # Create Roles
        roles = ["Admin", "ProjectManager", "Editor", "Author", "Typesetter"]
        for role_name in roles:
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                print(f"Creating role: {role_name}")
                role = Role(name=role_name, description=f"Role for {role_name}")
                db.add(role)
        db.commit()

        # Create Admin
        admin_email = "admin@example.com"
        # Explicitly hash using the context
        password_hash = pwd_context.hash("admin123")
        
        admin = db.query(User).filter(User.email == admin_email).first()
        if admin:
            db.delete(admin)
            db.commit()
            print("Deleted old admin")

        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        new_admin = User(
            username="admin",
            email=admin_email,
            password_hash=password_hash,
            is_active=True
        )
        new_admin.roles.append(admin_role)
        db.add(new_admin)
        db.commit()
        print(f"Admin reset. Hash: {password_hash}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_admin()
