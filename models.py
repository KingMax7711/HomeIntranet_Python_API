from sqlalchemy import Boolean, Column, ForeignKey, Integer, BigInteger, String, Date, DateTime, func
from database import Base

class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Real Information
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, index=True)
    password = Column(String)
    inscription_date = Column(Date, index=True, nullable=True)

    # Admin
    privileges = Column(String, index=True, nullable=True) # Owner / user
    # Version des refresh tokens : incrémentée pour invalider tous les anciens
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    # CGU & Privacy Policy acceptance
    accepted_cgu = Column(Boolean, default=False, nullable=False, server_default="false")
    accepted_privacy = Column(Boolean, default=False, nullable=False, server_default="false")
