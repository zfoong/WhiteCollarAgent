"""
Test script for Google Workspace token refresh functionality
"""
import sys
import time
from pathlib import Path

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary

# Initialize the library
GoogleWorkspaceAppLibrary.initialize()

def test_token_refresh():
    """
    Test the automatic token refresh by:
    1. Getting the current credential
    2. Manually setting token_expiry to a past time
    3. Calling a library method to trigger refresh
    """

    # Configuration - update these with your actual values
    user_id = "97590873-fa4a-41fe-ae0f-92ea668903a5"
    email = "ahmadajmal@craftos.net"  # Replace with your actual email

    print("=" * 60)
    print("Google Workspace Token Refresh Test")
    print("=" * 60)

    # Step 1: Get the current credential
    print("\n1. Fetching current credential...")
    credential = GoogleWorkspaceAppLibrary.get_credentials(user_id=user_id, email=email)

    if not credential:
        print(f"❌ No credential found for user_id={user_id}, email={email}")
        print("Please authenticate first before running this test.")
        return

    print(f"✓ Found credential for {credential.email}")
    print(f"  - Current token: {credential.token[:20]}...")
    print(f"  - Has refresh token: {bool(credential.refresh_token)}")
    print(f"  - Token expiry: {credential.token_expiry}")

    if not credential.refresh_token:
        print("\n❌ No refresh token available. Cannot test refresh.")
        return

    # Step 2: Force token expiry by setting it to past time
    print("\n2. Forcing token expiry...")
    credential.token_expiry = time.time() - 100  # Set to 100 seconds ago

    # Save the modified credential
    cred_store = GoogleWorkspaceAppLibrary.get_credential_store()
    cred_store.add(credential)
    print(f"✓ Set token_expiry to past time: {credential.token_expiry}")

    # Step 3: Call a library method that will trigger the refresh
    print("\n3. Calling read_recent_emails (this should trigger token refresh)...")
    print("-" * 60)

    result = GoogleWorkspaceAppLibrary.read_recent_emails(
        user_id=user_id,
        n=1,  # Just fetch 1 email to minimize API usage
        from_email=email
    )

    print("-" * 60)
    print(f"\n4. Result: {result.get('status')}")

    if result.get('status') == 'success':
        print("✓ API call succeeded!")
        print(f"  - Fetched {len(result.get('emails', []))} email(s)")

        # Check if token was refreshed
        updated_credential = GoogleWorkspaceAppLibrary.get_credentials(user_id=user_id, email=email)
        if updated_credential:
            print(f"\n5. Updated credential:")
            print(f"  - New token: {updated_credential.token[:20]}...")
            print(f"  - New expiry: {updated_credential.token_expiry}")

            if updated_credential.token_expiry and updated_credential.token_expiry > time.time():
                print(f"  - ✓ Token is now valid for ~{int((updated_credential.token_expiry - time.time()) / 60)} minutes")
                print("\n🎉 TOKEN REFRESH TEST PASSED!")
            else:
                print("  - ⚠ Token expiry still looks invalid")
    else:
        print(f"❌ API call failed: {result.get('reason')}")
        print("Check that GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set correctly.")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_token_refresh()
