# Qwen Authentication

This document explains how to authenticate with Qwen for use with the proxy server. The proxy server supports two methods for authentication: using the built-in authentication script or the official `qwen-code` CLI tool.

## Overview

The authentication system is built on the **OAuth 2.0 Device Authorization Flow**. This is a standard protocol that allows command-line interfaces (CLIs) and other input-constrained devices to obtain access tokens securely.

The proxy server now includes its own built-in authentication implementation based on the same OAuth 2.0 Device Authorization Flow used by the official `qwen-code` CLI tool.

## Authentication Methods

### Method 1: Built-in Authentication (Recommended)

The proxy server now includes its own built-in authentication script that implements the OAuth 2.0 Device Authorization Flow:

1. Run `npm run auth` in the project directory
2. The script will automatically:
   - Check for existing valid credentials
   - Attempt to refresh expired credentials if found
   - Initiate a new authentication flow if needed
3. You'll be presented with a QR code and URL to authenticate
4. Scan the QR code or visit the URL to complete authentication
5. The credentials will be automatically saved to `~/.qwen/oauth_creds.json`

### Method 2: Official qwen-code CLI Tool

You can also use the official `qwen-code` CLI tool from [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code):

1. Install the `qwen-code` CLI tool
2. Run `qwen-code auth` to authenticate with your Qwen account
3. The credentials will be saved to `~/.qwen/oauth_creds.json`

## Authentication Flow

The OAuth 2.0 Device Authorization Flow works as follows:

1.  **Initiation**: The client generates a **PKCE (Proof Key for Code Exchange)** pair, which consists of a `code_verifier` and a `code_challenge`. This is a security measure to prevent authorization code interception attacks.

2.  **Device Authorization Request**: The client sends a `POST` request to the `device_code` endpoint with the `code_challenge`.

3.  **User Authorization**: The server responds with a `verification_uri` and a `user_code`. The user is prompted to open the URI in a browser and enter the code to authorize the application.

4.  **Token Polling**: While the user is authorizing, the client continuously polls the `token` endpoint, sending the `device_code` and the original `code_verifier`.

5.  **Token Issuance**: Once the user completes the authorization, the server validates the `code_verifier` and, if successful, returns an `access_token`, a `refresh_token`, and the token's `expiry_date`.

6.  **Credential Caching**: The client saves these tokens to a file at `~/.qwen/oauth_creds.json`.

## Key Implementation Details

### Endpoints and Configuration

*   **Device Code Endpoint**: `https://chat.qwen.ai/api/v1/oauth2/device/code`
*   **Token Endpoint**: `https://chat.qwen.ai/api/v1/oauth2/token`
*   **Client ID**: `f0304373b74a44d2b584a3fb70ca9e56`
*   **Scope**: `openid profile email model.completion`

These constants are defined at the top of the `qwenOAuth2.ts` file.

### Token Storage

*   **Location**: The `getQwenCachedCredentialPath` function constructs the path to the credentials file: `~/.qwen/oauth_creds.json`.
*   **Functions**:
    *   `cacheQwenCredentials`: Writes the tokens to the file.
    *   `loadCachedQwenCredentials`: Reads the tokens from the file.
    *   `clearQwenCredentials`: Deletes the file to log the user out.

### Token Refresh

*   **Trigger**: The `isTokenValid` method checks if the current `access_token` will expire within the next 30 seconds.
*   **Mechanism**: If the token is close to expiring, the `refreshAccessToken` method is called. It sends the `refresh_token` to the token endpoint to get a new `access_token`.
*   **Automatic Refresh**: This process is handled automatically by the `getAccessToken` method, ensuring that the user always has a valid token without needing to re-authenticate manually.

This robust implementation of the OAuth 2.0 Device Flow is what allows the proxy server to seamlessly and securely authenticate with the Qwen API on the user's behalf.