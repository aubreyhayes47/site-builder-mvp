import re
import json
import os
import uuid
from werkzeug.utils import secure_filename
import shutil
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    make_response, current_app, send_from_directory
)
from markupsafe import Markup
from jinja2 import Environment, select_autoescape,  exceptions as jinja_exceptions # For rendering string templates
from flask_login import login_required, current_user
from .models import (
    db, User, PageTemplate, WebsiteProject, ProjectPage, ProjectAsset, NavbarItem
)
from .forms import (
    PageTemplateForm, WebsiteProjectForm, ProjectPageForm
)
import io
import zipfile


bp = Blueprint('main', __name__)

# --- Helper Functions ---

def extract_placeholders(html_content):
    """
    Extracts custom {{ placeholder.key }} style placeholders for form generation.
    This does NOT process Jinja2 logic.
    """
    if not html_content:
        return []
    # Regex to find {{ placeholder.key }} or {{ placeholder.key | filter }}
    # It captures the part inside {{ }} before any | filter or closing }}
    placeholders = set(re.findall(r"\{\{\s*([^}|]+?)\s*(?:\|.*?)?\}\}", html_content))
    
    valid_form_placeholders = set()
    for p_raw in placeholders:
        p = p_raw.strip()
        # Basic validation: must contain a dot (for nesting like hero.title) OR be a simple identifier.
        # Avoids complex Jinja like {% for item in items %} or {{ config.value }}.
        # This logic can be refined if template syntax for placeholders becomes more complex.
        if '.' in p or not any(c in p for c in ' %(){}\'"[]'): # Exclude common Jinja constructs
            valid_form_placeholders.add(p)
            
    return sorted(list(valid_form_placeholders))

# MODIFIED _build_context_from_flat_dict
def _build_context_from_flat_dict(flat_dict, project_id=None, export_mode=False, relative_image_path_prefix="assets/images"):
    """
    Converts a flat dictionary with dot-notation keys (e.g., "hero.title")
    into a nested dictionary suitable for Jinja2 context.
    If export_mode is True, generates relative paths for images.
    Otherwise, converts image filenames to full URLs for live preview.
    """
    context = {}
    if not flat_dict:
        return context

    for key, value in flat_dict.items():
        parts = key.split('.')
        current_level = context
        for i, part_name in enumerate(parts):
            part_name = part_name.strip()
            if i == len(parts) - 1: # Last part, assign the value
                is_image_key = 'image' in key.lower() or \
                               key.lower().endswith('_src') or \
                               key.lower().endswith('_url')
                
                current_value_str = str(value) if value is not None else ''

                if is_image_key and current_value_str: # Process if it's an image key and has a value
                    if export_mode:
                        # For export, use relative paths
                        current_level[part_name] = f"{relative_image_path_prefix.strip('/')}/{current_value_str}"
                    elif project_id and not current_value_str.startswith('/') and \
                         not current_value_str.startswith(('http://', 'https://')):
                        # For live preview, generate full URLs
                        try:
                            if request: 
                                 current_level[part_name] = url_for('main.serve_asset', project_id=project_id, asset_type='images', filename=current_value_str)
                            else: 
                                with current_app.app_context():
                                    current_level[part_name] = url_for('main.serve_asset', project_id=project_id, asset_type='images', filename=current_value_str)
                        except Exception as e:
                            current_app.logger.error(f"Error building URL for asset '{current_value_str}' in context (key: {key}): {e}")
                            current_level[part_name] = f"/uploads/{project_id}/images/{current_value_str}" # Fallback path for live preview
                    else:
                        # If it's already a full URL or no project_id for url_for, use as is
                        current_level[part_name] = current_value_str
                else:
                    # Not an image key, or no value, or already a full path/URL
                    current_level[part_name] = current_value_str
            else:
                current_level = current_level.setdefault(part_name, {})
    return context


# MODIFIED render_final_page_html
def render_final_page_html(raw_template_html, content_data_dict, global_css="", project=None, page_obj=None, 
                           export_mode=False, asset_path_config=None):
    """
    Renders the final HTML for a page.
    - Injects navbar, theme CSS, favicon, global CSS.
    - If export_mode is True, asset paths (images, favicon) are made relative based on asset_path_config.
    """
    current_app.logger.debug(
        f"Starting render_final_page_html (export_mode: {export_mode}) for page_id: {page_obj.id if page_obj else 'N/A'}, "
        f"project_id: {project.id if project and project.id else 'N/A'}"
    )

    processed_html_string = str(raw_template_html) if raw_template_html is not None else ""

    # --- Stage 1: Pre-processing and Injection ---
    nav_marker = 'CUSTOM MARKER' 
    navbar_html_content = ""

    if project:
        navbar_items_query = NavbarItem.query.filter_by(website_project_id=project.id)\
            .join(ProjectPage, NavbarItem.project_page_id == ProjectPage.id)\
            .order_by(NavbarItem.order).all()

        if navbar_items_query:
            navbar_html_list = []
            for item in navbar_items_query:
                # Navbar links are relative to HTML file location, good for static export too.
                page_url = f"{item.page.slug}.html" if item.page and item.page.slug else "#"
                navbar_html_list.append(f'<li><a href="{page_url}">{Markup.escape(item.link_text)}</a></li>')
            if navbar_html_list:
                navbar_html_content = f"<nav class=\"site-navbar\"><ul>{''.join(navbar_html_list)}</ul></nav>"
        
        if navbar_html_content:
            if nav_marker in processed_html_string:
                processed_html_string = processed_html_string.replace(nav_marker, Markup(navbar_html_content))
            else:
                body_match = re.search(r'(<body[^>]*>)', processed_html_string, flags=re.IGNORECASE)
                if body_match:
                    insert_pos = body_match.end()
                    part1 = processed_html_string[:insert_pos]
                    part2 = processed_html_string[insert_pos:]
                    processed_html_string = str(part1) + str(Markup(navbar_html_content)) + str(part2)
                else:
                    processed_html_string = str(Markup(navbar_html_content)) + processed_html_string

    head_injections = []
    if project:
        theme_colors_css_vars = []
        if project.primary_color:
            theme_colors_css_vars.append(f"  --theme-primary-color: {Markup.escape(project.primary_color)};")
        if project.secondary_color:
            theme_colors_css_vars.append(f"  --theme-secondary-color: {Markup.escape(project.secondary_color)};")
        if project.accent_color:
            theme_colors_css_vars.append(f"  --theme-accent-color: {Markup.escape(project.accent_color)};")
        
        if theme_colors_css_vars:
            head_injections.append(
                "<style id=\"theme-colors-vars\">\n:root {\n" +
                "\n".join(theme_colors_css_vars) +
                "\n}\n</style>"
            )

        if project.favicon_path:
            favicon_url = ""
            if export_mode and asset_path_config:
                favicon_folder_in_zip = asset_path_config.get('favicon', 'favicons') # Default from export config
                favicon_url = f"{favicon_folder_in_zip.strip('/')}/{project.favicon_path}"
            else:
                try:
                    favicon_url = url_for('main.serve_asset', project_id=project.id, asset_type='favicons', filename=project.favicon_path, _external=False)
                except Exception as e:
                    current_app.logger.error(f"Error generating favicon URL for project {project.id}, favicon '{project.favicon_path}': {e}")
            
            if favicon_url:
                ext = project.favicon_path.rsplit('.', 1)[-1].lower()
                mime_type_map = {"ico": "image/x-icon", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}
                mime_type = mime_type_map.get(ext, "image/vnd.microsoft.icon")
                head_injections.append(f'<link rel="icon" type="{mime_type}" href="{favicon_url}">')

    if global_css:
        head_injections.append(f"<style id=\"global-project-css\">\n{global_css}\n</style>")

    if head_injections:
        combined_head_html = Markup("\n".join(head_injections) + "\n")
        head_close_match = re.search(r'(</head>)', processed_html_string, flags=re.IGNORECASE)
        if head_close_match:
            insert_pos = head_close_match.start()
            part1 = processed_html_string[:insert_pos]
            part2 = processed_html_string[insert_pos:]
            processed_html_string = str(part1) + str(combined_head_html) + str(part2)
        else:
            if isinstance(processed_html_string, Markup):
                 processed_html_string = combined_head_html + processed_html_string
            else:
                 processed_html_string = str(combined_head_html) + processed_html_string

    # --- Stage 2: Render the processed string as a Jinja2 template ---
    final_rendered_html = ""
    template_context = {} 

    try:
        jinja_env = Environment(
            loader=None, 
            autoescape=select_autoescape(['html', 'xml']),
        )
        jinja_env.globals['url_for'] = url_for
        
        project_id_for_context = project.id if project and project.id else None
        image_relative_path_prefix = ""
        if export_mode and asset_path_config:
            image_relative_path_prefix = asset_path_config.get('image', 'assets/images')

        template_context = _build_context_from_flat_dict(
            content_data_dict, 
            project_id_for_context,
            export_mode=export_mode,
            relative_image_path_prefix=image_relative_path_prefix
        )
        
        if project:
            template_context['project'] = project 
        if page_obj:
            template_context['page'] = page_obj
        
        current_app.logger.debug(f"Rendering Jinja template for export_mode={export_mode} with context keys: {list(template_context.keys())}")
        
        final_template = jinja_env.from_string(str(processed_html_string))
        final_rendered_html = final_template.render(template_context)
        current_app.logger.debug("Jinja template rendered successfully.")

    except jinja_exceptions.TemplateSyntaxError as e:
        # ... (existing error handling for TemplateSyntaxError, ensure Markup.escape(str(processed_html_string))) ...
        error_type_name = type(e).__name__
        error_message_from_exception = str(e)
        line_info = f" (This error occurred near line {e.lineno} of the processed template string shown below)" if hasattr(e, 'lineno') and e.lineno is not None else " (Line number not available)"
        current_app.logger.error(f"Jinja2 TemplateSyntaxError: {error_message_from_exception}{line_info}", exc_info=True)
        error_detail_for_user_str = Markup.escape(f"{error_message_from_exception}{line_info}")
        # ... (rest of the f-string for error display, ensure it uses Markup.escape for dynamic parts)
        final_rendered_html = f"""<div style='border: 3px solid red; padding: 15px;'><h2>Template Error</h2><p>Type: {Markup.escape(error_type_name)}</p><p>Message: {error_detail_for_user_str}</p><pre>{Markup.escape(str(processed_html_string))}</pre></div>"""


    except Exception as e: 
        error_type_name_generic = type(e).__name__
        current_app.logger.error(
            f"Unexpected {error_type_name_generic} in render_final_page_html: {str(e)}",
            exc_info=True
        )
        error_detail_for_user_str_generic = Markup.escape(str(e))
        # ... (rest of the f-string for generic error display)
        final_rendered_html = f"""<div style='border: 2px solid orangered; padding: 10px;'><h2>Unexpected Error</h2><p>Type: {Markup.escape(error_type_name_generic)}</p><p>Details: {error_detail_for_user_str_generic}</p></div>"""
        
    return final_rendered_html


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


# --- Index Route ---
@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page_templates_sample = PageTemplate.query.order_by(PageTemplate.name).limit(5).all()
    page_templates_count = PageTemplate.query.count()
    website_projects_sample = WebsiteProject.query.order_by(WebsiteProject.project_name).limit(5).all()
    website_projects_count = WebsiteProject.query.count()
    
    return render_template('main/dashboard.html', title='Dashboard', current_user=current_user,
                             page_templates_sample=page_templates_sample,
                             page_templates_count=page_templates_count,
                             website_projects_sample=website_projects_sample,
                             website_projects_count=website_projects_count)

# --- Page Template Routes ---
@bp.route('/templates')
@login_required
def list_templates():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    templates_pagination = PageTemplate.query.order_by(PageTemplate.name).paginate(page=page, per_page=per_page, error_out=False)
    templates = templates_pagination.items
    return render_template('main/list_templates.html', title='Page Templates', templates=templates, pagination=templates_pagination, current_user=current_user)

@bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def new_template():
    form = PageTemplateForm()
    if form.validate_on_submit():
        existing_template = PageTemplate.query.filter_by(name=form.name.data).first()
        if existing_template:
            flash('A template with this name already exists. Please choose a different name.', 'warning')
        else:
            new_template_obj = PageTemplate(
                name=form.name.data,
                description=form.description.data,
                html_content=form.html_content.data
            )
            db.session.add(new_template_obj)
            db.session.commit()
            flash(f'Template "{new_template_obj.name}" created successfully!', 'success')
            return redirect(url_for('main.list_templates'))
    return render_template('main/template_form.html', title='New Page Template', form=form, legend='Create New Template', current_user=current_user)

@bp.route('/templates/edit/<int:template_id>', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    template_to_edit = PageTemplate.query.get_or_404(template_id)
    form = PageTemplateForm(obj=template_to_edit)
    if form.validate_on_submit():
        if form.name.data != template_to_edit.name: 
            existing_template_with_new_name = PageTemplate.query.filter_by(name=form.name.data).first()
            if existing_template_with_new_name:
                flash('Another template with this name already exists. Please choose a different name.', 'warning')
                return render_template('main/template_form.html', title='Edit Page Template', form=form, legend=f'Edit Template: {template_to_edit.name}', current_user=current_user)
        
        template_to_edit.name = form.name.data
        template_to_edit.description = form.description.data
        template_to_edit.html_content = form.html_content.data
        db.session.commit()
        flash(f'Template "{template_to_edit.name}" updated successfully!', 'success')
        return redirect(url_for('main.list_templates'))
    return render_template('main/template_form.html', title='Edit Page Template', form=form, legend=f'Edit Template: {template_to_edit.name}', current_user=current_user)

@bp.route('/templates/delete/<int:template_id>', methods=['POST'])
@login_required
def delete_template(template_id):
    template_to_delete = PageTemplate.query.get_or_404(template_id)
    if template_to_delete.used_by_pages.first():
        flash(f'Template "{template_to_delete.name}" cannot be deleted because it is in use by one or more project pages.', 'danger')
        return redirect(url_for('main.list_templates'))
    
    template_name = template_to_delete.name
    db.session.delete(template_to_delete)
    db.session.commit()
    flash(f'Template "{template_name}" deleted successfully.', 'success')
    return redirect(url_for('main.list_templates'))

# --- Website Project Routes ---
@bp.route('/projects')
@login_required
def list_projects():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    projects_pagination = WebsiteProject.query.order_by(WebsiteProject.project_name).paginate(page=page, per_page=per_page, error_out=False)
    projects = projects_pagination.items
    return render_template('main/list_projects.html', title='Website Projects', projects=projects, pagination=projects_pagination, current_user=current_user)

@bp.route('/projects/new', methods=['GET', 'POST'])
@login_required
def new_project():
    form = WebsiteProjectForm()
    if form.validate_on_submit():
        existing_project = WebsiteProject.query.filter_by(project_name=form.project_name.data).first()
        if existing_project:
            flash('A project with this name already exists. Please choose a different name.', 'warning')
        else:
            new_project_obj = WebsiteProject(
                project_name=form.project_name.data,
                site_title=form.site_title.data,
                global_css=form.global_css.data,
                primary_color=form.primary_color.data if form.primary_color.data else None,
                secondary_color=form.secondary_color.data if form.secondary_color.data else None,
                accent_color=form.accent_color.data if form.accent_color.data else None
            )
            
            favicon_file_to_save = None
            favicon_original_filename = None
            
            if form.favicon.data:
                file = form.favicon.data
                if file.filename and allowed_file(file.filename):
                    favicon_original_filename = secure_filename(file.filename)
                    extension = favicon_original_filename.rsplit('.', 1)[1].lower()
                    stored_filename_stem = f"favicon_{uuid.uuid4().hex[:8]}"
                    new_project_obj.favicon_path = f"{stored_filename_stem}.{extension}" 
                    favicon_file_to_save = file 
                elif file.filename: 
                    flash('Invalid favicon file type for new project. Favicon not saved.', 'warning')
            
            db.session.add(new_project_obj)
            try:
                db.session.commit() 

                if favicon_file_to_save and new_project_obj.favicon_path:
                    favicon_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(new_project_obj.id), 'favicons')
                    os.makedirs(favicon_folder, exist_ok=True)
                    file_path = os.path.join(favicon_folder, new_project_obj.favicon_path)
                    favicon_file_to_save.save(file_path)

                    asset = ProjectAsset(
                        website_project_id=new_project_obj.id,
                        asset_type='favicon',
                        original_filename=favicon_original_filename, 
                        stored_filename=new_project_obj.favicon_path
                    )
                    db.session.add(asset)
                    db.session.commit()

                flash(f'Project "{new_project_obj.project_name}" created successfully!', 'success')
                return redirect(url_for('main.list_projects'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating project: {str(e)}', 'danger')
                current_app.logger.error(f"Error creating project: {e}")

    return render_template('main/project_form.html', title='New Website Project', form=form, legend='Create New Project', current_user=current_user, project_to_edit=None)


@bp.route('/projects/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project_to_edit = WebsiteProject.query.get_or_404(project_id)
    form = WebsiteProjectForm(obj=project_to_edit) 

    if form.validate_on_submit():
        if form.project_name.data != project_to_edit.project_name:
            existing_project_with_new_name = WebsiteProject.query.filter_by(project_name=form.project_name.data).first()
            if existing_project_with_new_name:
                flash('Another project with this name already exists. Please choose a different name.', 'warning')
                return render_template('main/project_form.html', title='Edit Website Project', form=form, legend=f'Edit Project: {project_to_edit.project_name}', current_user=current_user, project_to_edit=project_to_edit)
        
        project_to_edit.project_name = form.project_name.data
        project_to_edit.site_title = form.site_title.data
        project_to_edit.global_css = form.global_css.data
        project_to_edit.primary_color = form.primary_color.data if form.primary_color.data else None
        project_to_edit.secondary_color = form.secondary_color.data if form.secondary_color.data else None
        project_to_edit.accent_color = form.accent_color.data if form.accent_color.data else None

        if form.favicon.data: 
            file = form.favicon.data
            if file.filename and allowed_file(file.filename):
                original_filename = secure_filename(file.filename)
                extension = original_filename.rsplit('.', 1)[1].lower()
                stored_filename_stem = f"favicon_{uuid.uuid4().hex[:8]}"
                stored_filename = f"{stored_filename_stem}.{extension}"
                
                favicon_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(project_to_edit.id), 'favicons')
                os.makedirs(favicon_folder, exist_ok=True)
                file_path = os.path.join(favicon_folder, stored_filename)

                if project_to_edit.favicon_path and project_to_edit.favicon_path != stored_filename:
                    old_asset = ProjectAsset.query.filter_by(
                        website_project_id=project_to_edit.id,
                        asset_type='favicon',
                        stored_filename=project_to_edit.favicon_path
                    ).first()
                    if old_asset:
                        old_file_path_on_disk = os.path.join(current_app.config['UPLOAD_FOLDER'], str(project_to_edit.id), 'favicons', old_asset.stored_filename)
                        if os.path.exists(old_file_path_on_disk):
                            try:
                                os.remove(old_file_path_on_disk)
                            except OSError as e:
                                current_app.logger.error(f"Error deleting old favicon file {old_file_path_on_disk}: {e}")
                        db.session.delete(old_asset)
                
                file.save(file_path)
                
                asset = ProjectAsset.query.filter_by(website_project_id=project_to_edit.id, asset_type='favicon', stored_filename=stored_filename).first()
                if not asset:
                    asset = ProjectAsset(
                        website_project_id=project_to_edit.id,
                        asset_type='favicon',
                        original_filename=original_filename,
                        stored_filename=stored_filename
                    )
                    db.session.add(asset)
                project_to_edit.favicon_path = stored_filename
            elif file.filename: 
                flash('Invalid favicon file type. Favicon not updated.', 'warning')
        
        try:
            db.session.commit()
            flash(f'Project "{project_to_edit.project_name}" updated successfully!', 'success')
            return redirect(url_for('main.list_projects'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating project: {str(e)}', 'danger')
            current_app.logger.error(f"Error updating project {project_id}: {e}")

    return render_template('main/project_form.html', title='Edit Website Project', form=form, legend=f'Edit Project: {project_to_edit.project_name}', current_user=current_user, project_to_edit=project_to_edit)


@bp.route('/projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    project_to_delete = WebsiteProject.query.get_or_404(project_id)
    project_name = project_to_delete.project_name
    
    project_upload_root = os.path.join(current_app.config['UPLOAD_FOLDER'], str(project_to_delete.id))
    if os.path.exists(project_upload_root):
        try:
            shutil.rmtree(project_upload_root)
            current_app.logger.info(f"Deleted asset folder: {project_upload_root}")
        except OSError as e:
            current_app.logger.error(f"Error deleting asset folder {project_upload_root}: {e}")
            flash(f"Error deleting project assets for {project_name}. Please check server logs.", "danger")

    db.session.delete(project_to_delete)
    db.session.commit()
    flash(f'Project "{project_name}" and its associated items/assets have been deleted.', 'success')
    return redirect(url_for('main.list_projects'))

# --- Project Page Routes ---
@bp.route('/project/<int:project_id>/pages')
@login_required
def list_project_pages(project_id):
    project = WebsiteProject.query.get_or_404(project_id)
    project_pages_list = ProjectPage.query.filter_by(website_project_id=project.id).order_by(ProjectPage.title).all()
    return render_template('main/list_project_pages.html',
                             title=f'Pages for "{project.project_name}"',
                             project=project,
                             pages=project_pages_list,
                             current_user=current_user
                           ) # Corrected SyntaxError here

@bp.route('/project/<int:project_id>/pages/new', methods=['GET', 'POST'])
@login_required
def new_project_page(project_id):
    project = WebsiteProject.query.get_or_404(project_id)
    form = ProjectPageForm(request.form if request.method == 'POST' else None)

    available_templates = PageTemplate.query.order_by(PageTemplate.name).all()
    choices = [(str(pt.id), pt.name) for pt in available_templates]
    placeholder_choice = ('', '--- Select a Template ---')
    
    if not available_templates:
        form.page_template_id.choices = [('', '--- No Templates Available ---')]
    else:
        form.page_template_id.choices = [placeholder_choice] + choices
    
    if request.method == 'GET':
        current_app.logger.debug(f"GET new_project_page: form.page_template_id.data is '{form.page_template_id.data}' (type: {type(form.page_template_id.data)})")

    if form.validate_on_submit():
        selected_template_id = form.page_template_id.data 

        if selected_template_id is None: 
            flash('A template must be selected.', 'danger')
        elif not PageTemplate.query.get(selected_template_id): 
            flash('Selected template is invalid or does not exist.', 'danger')
        else:
            existing_page_with_slug = ProjectPage.query.filter_by(
                website_project_id=project.id,
                slug=form.slug.data
            ).first()
            if existing_page_with_slug:
                flash('A page with this slug already exists for this project. Please choose a different slug.', 'warning')
            else:
                new_page = ProjectPage(
                    title=form.title.data,
                    slug=form.slug.data,
                    page_template_id=selected_template_id,
                    website_project_id=project.id
                )
                db.session.add(new_page)
                db.session.commit()
                flash(f'Page "{new_page.title}" created successfully!', 'success')
                return redirect(url_for('main.list_project_pages', project_id=project.id))
        
    return render_template('main/project_page_form.html',
                             title=f'New Page for "{project.project_name}"',
                             form=form,
                             project=project,
                             legend='Create New Page',
                             current_user=current_user)

@bp.route('/project/<int:project_id>/pages/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def edit_project_page_settings(project_id, page_id):
    project = WebsiteProject.query.get_or_404(project_id)
    page_to_edit = ProjectPage.query.filter_by(id=page_id, website_project_id=project.id).first_or_404()
    form = ProjectPageForm(request.form if request.method == 'POST' else None, obj=page_to_edit)

    available_templates = PageTemplate.query.order_by(PageTemplate.name).all()
    choices = [(str(pt.id), pt.name) for pt in available_templates]
    form.page_template_id.choices = [('', '--- Select a Template ---')] + choices
    if not available_templates:
        form.page_template_id.choices = [('', '--- No Templates Available ---')]
    
    if request.method == 'GET' and page_to_edit.page_template_id:
        form.page_template_id.data = page_to_edit.page_template_id 

    if form.validate_on_submit():
        selected_template_id = form.page_template_id.data 

        if selected_template_id is None:
             flash('A template must be selected.', 'danger')
        elif not PageTemplate.query.get(selected_template_id):
            flash('Selected template is invalid or does not exist.', 'danger')
        else:
            if form.slug.data != page_to_edit.slug:
                existing_page_with_new_slug = ProjectPage.query.filter(
                    ProjectPage.website_project_id == project.id,
                    ProjectPage.slug == form.slug.data,
                    ProjectPage.id != page_to_edit.id
                ).first()
                if existing_page_with_new_slug:
                    flash('Another page in this project already has this slug. Please choose a different slug.', 'warning')
                    return render_template('main/project_page_form.html',
                                           title=f'Edit Page Settings for "{page_to_edit.title}"',
                                           form=form, project=project, legend='Edit Page Settings',
                                           current_user=current_user)
            
            page_to_edit.title = form.title.data
            page_to_edit.slug = form.slug.data
            page_to_edit.page_template_id = selected_template_id
            
            db.session.commit()
            flash(f'Page settings for "{page_to_edit.title}" updated successfully!', 'success')
            return redirect(url_for('main.list_project_pages', project_id=project.id))
    
    return render_template('main/project_page_form.html',
                           title=f'Edit Page Settings for "{page_to_edit.title}"',
                           form=form, project=project, legend='Edit Page Settings',
                           current_user=current_user)

@bp.route('/project/<int:project_id>/pages/delete/<int:page_id>', methods=['POST'])
@login_required
def delete_project_page(project_id, page_id):
    project = WebsiteProject.query.get_or_404(project_id)
    page_to_delete = ProjectPage.query.filter_by(id=page_id, website_project_id=project.id).first_or_404()
    page_title = page_to_delete.title
    db.session.delete(page_to_delete) 
    db.session.commit()
    flash(f'Page "{page_title}" has been deleted from project "{project.project_name}".', 'success')
    return redirect(url_for('main.list_project_pages', project_id=project.id))

@bp.route('/project/<int:project_id>/page/<int:page_id>/edit_content', methods=['GET', 'POST'])
@login_required
def edit_page_content(project_id, page_id):
    project = WebsiteProject.query.get_or_404(project_id)
    page = ProjectPage.query.filter_by(id=page_id, website_project_id=project.id).first_or_404()

    if not page.template:
        flash('This page does not have an associated template. Cannot edit content.', 'danger')
        return redirect(url_for('main.list_project_pages', project_id=project.id))

    placeholders = extract_placeholders(page.template.html_content)
    current_content = {}
    if page.content_data_json:
        try:
            current_content = json.loads(page.content_data_json)
        except json.JSONDecodeError:
            flash('Error loading existing page content. It might be corrupted.', 'warning')
            current_app.logger.error(f"JSONDecodeError for page ID {page.id} content: {page.content_data_json}")
            current_content = {}

    if request.method == 'POST':
        new_content_data = {}
        form_had_errors = False

        for placeholder_key_raw in placeholders:
            placeholder_key = placeholder_key_raw.strip()
            is_image_key = 'image' in placeholder_key.lower() or \
                           placeholder_key.lower().endswith('_src') or \
                           placeholder_key.lower().endswith('_url')
            file_input_name = f"{placeholder_key}_file"

            if is_image_key and file_input_name in request.files:
                file = request.files[file_input_name]
                if file and file.filename and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    extension = original_filename.rsplit('.', 1)[1].lower()
                    stored_filename_stem = uuid.uuid4().hex
                    stored_filename = f"{stored_filename_stem}.{extension}"
                    project_asset_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(project.id), 'images')
                    os.makedirs(project_asset_folder, exist_ok=True)
                    file_path = os.path.join(project_asset_folder, stored_filename)
                    file.save(file_path)
                    asset = ProjectAsset(
                        website_project_id=project.id, asset_type='image',
                        original_filename=original_filename, stored_filename=stored_filename
                    )
                    db.session.add(asset)
                    new_content_data[placeholder_key] = stored_filename
                elif file and file.filename:
                    flash(f"File type for '{placeholder_key}' not allowed. Allowed: {', '.join(current_app.config['ALLOWED_EXTENSIONS'])}. Previous image kept.", 'warning')
                    new_content_data[placeholder_key] = current_content.get(placeholder_key, '')
                    form_had_errors = True
                else:
                    new_content_data[placeholder_key] = request.form.get(placeholder_key, current_content.get(placeholder_key, ''))
            else:
                new_content_data[placeholder_key] = request.form.get(placeholder_key, '')
        
        page.content_data_json = json.dumps(new_content_data)
        try:
            db.session.commit()
            if not form_had_errors:
                 flash(f'Content for page "{page.title}" updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving content: {str(e)}', 'danger')
            current_app.logger.error(f"Error saving content for page {page.id}: {e}")
        return redirect(url_for('main.edit_page_content', project_id=project.id, page_id=page.id))

    return render_template('main/edit_page_content.html',
                             title=f'Edit Content for "{page.title}"',
                             project=project, page=page, placeholders=placeholders,
                             current_content=current_content, current_user=current_user,
                             legend=f'Edit Content: {page.title}')

# --- Navbar Management Route ---
@bp.route('/project/<int:project_id>/navbar', methods=['GET', 'POST'])
@login_required
def manage_navbar(project_id):
    project = WebsiteProject.query.get_or_404(project_id)
    pages_for_navbar = ProjectPage.query.filter_by(website_project_id=project.id).order_by(ProjectPage.title).all()

    if request.method == 'POST':
        NavbarItem.query.filter_by(website_project_id=project.id).delete() 

        new_navbar_items_to_add = []
        for page_item in pages_for_navbar: 
            page_id_str = str(page_item.id)
            if f'page_in_navbar_{page_id_str}' in request.form: 
                link_text = request.form.get(f'link_text_{page_id_str}', page_item.title).strip()
                order_str = request.form.get(f'order_{page_id_str}', '0')
                try:
                    order = int(order_str)
                except ValueError:
                    order = 0 
                
                nav_item = NavbarItem(
                    website_project_id=project.id,
                    project_page_id=page_item.id,
                    link_text=link_text if link_text else page_item.title, 
                    order=order
                )
                new_navbar_items_to_add.append(nav_item)
        
        if new_navbar_items_to_add:
            db.session.add_all(new_navbar_items_to_add)
        
        try:
            db.session.commit()
            flash('Navbar updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating navbar: {str(e)}', 'danger')
            current_app.logger.error(f"Error updating navbar for project {project.id}: {e}")
        return redirect(url_for('main.manage_navbar', project_id=project.id))

    current_navbar_items = NavbarItem.query.filter_by(website_project_id=project.id).all()
    current_navbar_config = {
        item.project_page_id: {'link_text': item.link_text, 'order': item.order, 'in_navbar': True}
        for item in current_navbar_items
    }
    
    return render_template('main/manage_navbar.html',
                             title=f'Manage Navbar for "{project.project_name}"',
                             project=project,
                             pages=pages_for_navbar, 
                             current_navbar_config=current_navbar_config,
                             current_user=current_user)


# ---- Route to Serve Uploaded Assets ----
@bp.route('/uploads/<int:project_id>/<path:asset_type>/<path:filename>')
@login_required
def serve_asset(project_id, asset_type, filename):
    safe_asset_types = ['images', 'css', 'js', 'favicons']
    if asset_type not in safe_asset_types:
        current_app.logger.warning(f"Attempt to serve invalid asset type: {asset_type}")
        return "Invalid asset type", 404
        
    directory = os.path.join(current_app.config['UPLOAD_FOLDER'], str(project_id), asset_type)
    
    abs_path_to_file = os.path.abspath(os.path.join(directory, filename))
    abs_directory_path = os.path.abspath(directory)

    if not abs_path_to_file.startswith(abs_directory_path):
        current_app.logger.warning(f"Path traversal attempt: {filename} from {directory}")
        return "Forbidden", 403 
        
    return send_from_directory(directory, filename)


# Ensure your preview_page route calls render_final_page_html WITHOUT export flags:
@bp.route('/preview/page/<int:page_id>')
@login_required
def preview_page(page_id):
    page = ProjectPage.query.get_or_404(page_id)

    if not page.template:
        return "Error: This page has no template assigned.", 404
    if not page.website_project:
        current_app.logger.error(f"Consistency error: Page ID {page.id} has no website_project associated.")
        return "Error: This page is not associated with a project.", 404

    template_html = page.template.html_content
    current_app.logger.debug(f"RAW HTML FROM DB for template ID {page.template.id}: >>>{template_html[:200]}<<<") # Keep this helpful log
    
    content_data_from_db = {}
    if page.content_data_json:
        try:
            content_data_from_db = json.loads(page.content_data_json)
        except json.JSONDecodeError:
            current_app.logger.error(f"JSONDecodeError for page ID {page.id} content: {page.content_data_json}")
            pass # content_data_from_db remains empty

    global_css = page.website_project.global_css if page.website_project.global_css else ""

    rendered_html = render_final_page_html(
        raw_template_html=template_html,
        content_data_dict=content_data_from_db, 
        global_css=global_css,
        project=page.website_project, 
        page_obj=page,
        export_mode=False, # Explicitly False for preview
        asset_path_config=None # Not needed for preview
    )

    response = make_response(rendered_html)
    response.headers['Content-Type'] = 'text/html'
    return response

# NEW/REVISED export_project_zip route
@bp.route('/project/<int:project_id>/export_zip')
@login_required
def export_project_zip(project_id):
    project = WebsiteProject.query.get_or_404(project_id)
    pages = ProjectPage.query.filter_by(website_project_id=project.id).all()
    # Fetch assets that have a stored_filename, as these are expected to be on disk
    assets = ProjectAsset.query.filter(
        ProjectAsset.website_project_id == project.id,
        ProjectAsset.stored_filename.isnot(None)
    ).all()

    memory_file = io.BytesIO()

    asset_paths_in_zip_config = {
        'image': 'assets/images',  # Where images from content_data_json will be linked from (relative to HTML files)
        'favicon': 'assets/favicons' # Where favicon will be linked from (relative to HTML files)
        # Note: This config tells render_final_page_html how to construct relative URLs.
        # The actual placement in the zip is handled below.
    }
    
    # Define where asset types from ProjectAsset are stored on disk relative to UPLOAD_FOLDER/<project_id>/
    # This should match your `serve_asset` route's subfolder logic.
    asset_type_disk_folders = {
        'image': 'images',
        'favicon': 'favicons',
        # Add other types if your ProjectAsset.asset_type can be other things like 'css', 'js'
    }

    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # --- 1. Render and add HTML pages ---
        for page in pages:
            if not page.template:
                current_app.logger.warning(f"Page '{page.title}' (ID: {page.id}) in project {project_id} has no template, skipping for export.")
                continue

            template_html = page.template.html_content
            content_data = json.loads(page.content_data_json) if page.content_data_json else {}
            global_css_content = project.global_css if project.global_css else ""

            rendered_html = render_final_page_html(
                raw_template_html=template_html,
                content_data_dict=content_data,
                global_css=global_css_content,
                project=project,
                page_obj=page,
                export_mode=True, 
                asset_path_config=asset_paths_in_zip_config 
            )
            
            page_filename = f"{page.slug}.html" if page.slug else f"page_{page.id}.html"
            if page_filename == ".html" or page_filename == "None.html": # Handle empty or None slug
                 page_filename = f"page_{page.id}.html"
            if page.slug == 'index': # Common convention for homepage
                page_filename = 'index.html'

            zf.writestr(page_filename, rendered_html)
            current_app.logger.debug(f"Added HTML page '{page_filename}' to zip for project {project_id}")

        # --- 2. Add assets (images, favicons, etc.) ---
        for asset in assets:
            # Determine the folder for this asset type within the zip, from asset_paths_in_zip_config
            zip_folder_for_asset_type = asset_paths_in_zip_config.get(asset.asset_type)
            
            # Determine the subfolder on disk where this asset type is stored
            disk_subfolder_for_asset_type = asset_type_disk_folders.get(asset.asset_type)

            if not zip_folder_for_asset_type or not disk_subfolder_for_asset_type:
                current_app.logger.warning(f"Asset type '{asset.asset_type}' for asset ID {asset.id} (project {project_id}) has no defined zip path or disk folder mapping, skipping.")
                continue

            source_file_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                str(project.id),
                disk_subfolder_for_asset_type, 
                asset.stored_filename
            )

            path_in_zip = os.path.join(zip_folder_for_asset_type, asset.stored_filename)
            
            if os.path.exists(source_file_path):
                zf.write(source_file_path, path_in_zip)
                current_app.logger.debug(f"Added asset {source_file_path} as {path_in_zip} to zip for project {project_id}")
            else:
                current_app.logger.warning(f"Asset file not found on disk: {source_file_path} for asset ID {asset.id} (project {project_id}), skipping.")

    memory_file.seek(0)
    
    zip_download_name = f"{secure_filename(project.project_name if project.project_name else 'website')}_export.zip"

    # Ensure flask.send_file is imported
    from flask import send_file
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_download_name
    )
