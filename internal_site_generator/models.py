# ISG_Project/internal_site_generator/models.py
from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class PageTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(250))
    html_content = db.Column(db.Text, nullable=False) # Should contain ""
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # backref 'used_by_pages' created by ProjectPage.template relationship

    def __repr__(self):
        return f'<PageTemplate {self.name}>'

class WebsiteProject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(150), nullable=False, index=True, unique=True)
    site_title = db.Column(db.String(100), nullable=True)
    favicon_path = db.Column(db.String(255), nullable=True) # Stores stored_filename of the favicon ProjectAsset
    global_css = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Theme Colors
    primary_color = db.Column(db.String(7), nullable=True)   # e.g., #RRGGBB
    secondary_color = db.Column(db.String(7), nullable=True)
    accent_color = db.Column(db.String(7), nullable=True)

    pages = db.relationship('ProjectPage', backref='website_project', lazy='dynamic', cascade="all, delete-orphan")
    assets = db.relationship('ProjectAsset', backref='website_project', lazy='dynamic', cascade="all, delete-orphan")
    navbar_items = db.relationship('NavbarItem',
                                   backref='website_project',
                                   lazy='dynamic',
                                   order_by='NavbarItem.order',
                                   cascade="all, delete-orphan")

    def __repr__(self):
        return f'<WebsiteProject {self.project_name}>'

class ProjectPage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(150), nullable=False, index=True)
    
    website_project_id = db.Column(db.Integer, db.ForeignKey('website_project.id'), nullable=False)
    page_template_id = db.Column(db.Integer, db.ForeignKey('page_template.id'), nullable=False)

    content_data_json = db.Column(db.Text)
    
    meta_description = db.Column(db.String(255), nullable=True)
    meta_keywords = db.Column(db.String(255), nullable=True)

    # These fields are for default behavior if not overridden by NavbarItem specific settings.
    # Consider if these are still primary or if NavbarItem becomes the sole source for nav properties.
    # For MVP, keeping them can provide defaults for the NavbarItem.link_text.
    navbar_order = db.Column(db.Integer, default=0) # Might be superseded by NavbarItem.order
    show_in_navbar = db.Column(db.Boolean, default=True) # Might be superseded by existence of NavbarItem

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template = db.relationship('PageTemplate', backref=db.backref('used_by_pages', lazy='dynamic'))

    __table_args__ = (db.UniqueConstraint('website_project_id', 'slug', name='_website_project_slug_uc'),)

    def __repr__(self):
        return f'<ProjectPage {self.title} (Project ID: {self.website_project_id})>'

class ProjectAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    website_project_id = db.Column(db.Integer, db.ForeignKey('website_project.id'), nullable=False)
    asset_type = db.Column(db.String(50), nullable=False)  # 'image', 'css', 'js', 'favicon'
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True) # Unique filename on disk
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ProjectAsset {self.original_filename} (Type: {self.asset_type})>'

class NavbarItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    website_project_id = db.Column(db.Integer, db.ForeignKey('website_project.id'), nullable=False)
    project_page_id = db.Column(db.Integer, db.ForeignKey('project_page.id'), nullable=False) # For MVP, must link to a page
    link_text = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    page = db.relationship('ProjectPage', backref=db.backref('navbar_entries', lazy='dynamic', cascade="all, delete-orphan"))
    # Note: Cascade on backref from ProjectPage to NavbarItem means if a page is deleted, its navbar entries are deleted.

    def __repr__(self):
        return f'<NavbarItem {self.link_text} (Order: {self.order})>'
