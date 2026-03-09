from app.database import SessionLocal
from app.models import Role, User
from app.auth import hash_password

def seed_db():
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

        # Create/Update Admin User
        admin_email = "admin@example.com"
        admin = db.query(User).filter(User.email == admin_email).first()
        
        # New password hash
        new_hash = hash_password("admin123")

        if not admin:
            print(f"Creating admin user: {admin_email}")
            admin_role = db.query(Role).filter(Role.name == "Admin").first()
            admin = User(
                username="admin",
                email=admin_email,
                password_hash=new_hash,
                is_active=True
            )
            admin.roles.append(admin_role)
            db.add(admin)
        else:
            print(f"Updating admin user password: {admin_email}")
            admin.password_hash = new_hash
            db.add(admin)

        db.commit()
        print("Admin user updated successfully. Login with: admin / admin123")

    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
