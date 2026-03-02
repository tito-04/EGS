from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from app.models import User, RoleEnum
from app.schemas.user import UserCreate, RoleEnum as SchemaRoleEnum
from app.core.security import hash_password


class UserCRUD:
    """CRUD operations for User model."""
    
    @staticmethod
    async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
        """Create a new user."""
        # Convert schema role to model role
        role_map = {
            SchemaRoleEnum.FAN: RoleEnum.FAN,
            SchemaRoleEnum.PROMOTER: RoleEnum.PROMOTER,
            SchemaRoleEnum.ADMIN: RoleEnum.ADMIN,
        }
        
        db_user = User(
            email=user_create.email,
            full_name=user_create.full_name,
            hashed_password=hash_password(user_create.password),
            role=role_map.get(user_create.role, RoleEnum.FAN),
        )
        
        try:
            db.add(db_user)
            await db.commit()
            await db.refresh(db_user)
            return db_user
        except IntegrityError:
            await db.rollback()
            raise ValueError(f"User with email {user_create.email} already exists")
    
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
        """Get user by ID."""
        return await db.get(User, user_id)
    
    @staticmethod
    async def update_user(db: AsyncSession, user_id: str, **kwargs) -> User | None:
        """Update user attributes."""
        user = await db.get(User, user_id)
        if not user:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        await db.commit()
        await db.refresh(user)
        return user
    
    @staticmethod
    async def deactivate_user(db: AsyncSession, user_id: str) -> User | None:
        """Deactivate a user."""
        return await UserCRUD.update_user(db, user_id, is_active=False)
    
    @staticmethod
    async def activate_user(db: AsyncSession, user_id: str) -> User | None:
        """Activate a user."""
        return await UserCRUD.update_user(db, user_id, is_active=True)
