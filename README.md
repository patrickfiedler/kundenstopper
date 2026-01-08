# Kundenstopper

A Flask-based web application for displaying PDF files in a browser with automatic page cycling. Perfect for digital signage and displaying menus, announcements, or promotional materials.

## Features

- **Automatic PDF Cycling**: Display multi-page PDFs with automatic page advancement
- **Web-based Display**: View PDFs in fullscreen mode in any modern web browser
- **Admin Panel**: Secure interface for managing PDF files
- **File Management**: Upload, rename, delete, and select PDFs
- **Configurable Settings**: Adjust page cycling interval through the admin panel
- **Pagination**: Admin panel shows 10 files per page for easy navigation
- **Auto-selection**: Automatically displays the newest uploaded PDF by default
- **Local PDF.js**: Includes PDF.js library locally for offline operation

## Technology Stack

- **Backend**: Flask (Python web framework)
- **WSGI Server**: Waitress (production-ready WSGI server)
- **Authentication**: Flask-Login with bcrypt password hashing
- **Database**: SQLite (for metadata and settings)
- **PDF Rendering**: PDF.js (local copy)
- **Storage**: Local filesystem

## Quick Start

### Automated Installation (Recommended)

```bash
git clone https://github.com/parsnipsmoothie/kundenstopper.git
cd kundenstopper
./deploy.sh
```

The deployment script will guide you through the setup process interactively.

### Manual Installation

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed installation instructions, including:
- Manual setup steps
- Systemd service configuration
- Update procedures
- Troubleshooting

**Quick manual setup:**

1. **Clone the repository**
   ```bash
   git clone https://github.com/parsnipsmoothie/kundenstopper.git
   cd kundenstopper
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the application**
   ```bash
   python3 generate_password_hash.py  # Generate password hash
   cp config.json.example config.json
   # Edit config.json with your settings
   ```

4. **Create uploads directory**
   ```bash
   mkdir uploads
   ```

## Configuration

The `config.json` file contains the following settings:

- `admin_username`: Username for admin login (default: "admin")
- `admin_password_hash`: Bcrypt hash of the admin password
- `secret_key`: Flask secret key for session management (change this!)
- `port`: Port number to run the server on (default: 8080)
- `host`: Host address to bind to (default: "0.0.0.0" for all interfaces)
- `upload_folder`: Directory for storing uploaded PDFs (default: "uploads")

## Usage

### Starting the Server

```bash
python3 app.py
```

The server will start and display the URLs:
- Display URL: `http://localhost:8080/display`
- Admin URL: `http://localhost:8080/admin`

### Accessing the Application

1. **Display View** (`/display`):
   - Open this URL in a web browser (preferably Firefox)
   - Start browser in fullscreen mode from the operating system
   - PDF will display and automatically cycle through pages
   - The display checks for updates every 10 seconds

2. **Admin Panel** (`/admin`):
   - Login with your configured username and password
   - Upload new PDF files
   - Select which PDF to display
   - Set to show newest PDF automatically
   - Rename or delete existing PDFs
   - Adjust page cycling interval

### Admin Panel Features

- **Upload PDF**: Select and upload PDF files (max 100MB)
- **Select PDF**: Choose which PDF to display on the `/display` view
- **Show Newest PDF**: Automatically display the most recently uploaded PDF
- **Rename**: Click on a filename to edit it
- **Delete**: Remove PDFs from the system
- **Settings**: Adjust the page cycling interval (in seconds)
- **Pagination**: Navigate through multiple pages of PDF files (10 per page)

## Database

The application uses SQLite for storing:
- PDF file metadata (filename, original name, upload date, file size)
- Settings (selected PDF ID, cycling interval)

Database file: `kundenstopper.db` (created automatically on first run)

## File Structure

```
kundenstopper/
├── app.py                      # Main Flask application
├── config.py                   # Configuration management
├── models.py                   # Database models and functions
├── requirements.txt            # Python dependencies
├── deploy.sh                   # Automated deployment script
├── update.sh                   # Automated update script
├── config.json                 # Configuration file (create from example)
├── config.json.example         # Example configuration
├── generate_password_hash.py   # Utility to generate password hashes
├── kundenstopper.service       # Systemd service template
├── kundenstopper.db           # SQLite database (auto-created)
├── uploads/                    # PDF file storage
├── README.md                   # Usage documentation
├── DEPLOYMENT.md               # Deployment guide
├── INSTALLATION.md             # Installation instructions (German)
├── CLAUDE.md                   # Project guidance for Claude Code
├── LICENSE                     # MIT License
├── static/
│   ├── pdfjs/                 # PDF.js library files
│   ├── css/                   # Custom CSS files
│   └── js/                    # Custom JavaScript files
└── templates/
    ├── display.html           # PDF display view
    ├── admin.html             # Admin panel
    └── login.html             # Login page
```

## Security Notes

- Admin password is stored as bcrypt hash in config.json
- Session management handled by Flask-Login
- File uploads are restricted to PDF format
- Uploaded files are stored with unique UUID filenames
- Maximum upload size: 100MB

## Browser Compatibility

The application works best with modern browsers that support:
- HTML5 Canvas
- PDF.js
- ES6 JavaScript

Tested with:
- Firefox (recommended)
- Chrome
- Edge

## Updating

To update an existing installation to the latest version:

```bash
cd /path/to/kundenstopper
./update.sh
```

The update script will:
- Create a backup tag before updating
- Pull the latest code from GitHub
- Update dependencies if needed
- Restart the service automatically
- Provide rollback instructions if something goes wrong

For more details, see [DEPLOYMENT.md](DEPLOYMENT.md#updating-an-existing-installation).

## Troubleshooting

### PDF.js not loading
- Ensure the `static/pdfjs/build/` directory contains `pdf.min.js` and `pdf.worker.min.js`
- Check browser console for errors

### Cannot login
- Verify the password hash in `config.json` was generated correctly
- Run `generate_password_hash.py` again if needed

### PDF not displaying
- Check that at least one PDF has been uploaded
- Verify the uploads directory exists and is writable
- Check the browser console for errors

### Port already in use
- Change the `port` setting in `config.json`
- Or stop the process using the current port

## Development

To run in development mode with Flask's built-in server:

```python
# Modify app.py, replace the bottom section with:
if __name__ == '__main__':
    app.run(host=config.host, port=config.port, debug=True)
```

## License

This project uses PDF.js which is licensed under Apache License 2.0.

## Support

For issues and questions, please check:
- Browser console for JavaScript errors
- Server console for Python errors
- File permissions for uploads directory
