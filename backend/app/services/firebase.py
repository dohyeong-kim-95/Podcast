import os

import firebase_admin
from firebase_admin import credentials, auth, firestore


def init_firebase():
    """Initialize Firebase Admin SDK (idempotent)."""
    if firebase_admin._apps:
        return

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        # Cloud Run에서는 ADC(Application Default Credentials) 사용
        firebase_admin.initialize_app()


def get_firestore_client():
    init_firebase()
    return firestore.client()


def verify_id_token(token: str) -> dict:
    """Verify a Firebase ID token and return the decoded claims."""
    init_firebase()
    return auth.verify_id_token(token)
