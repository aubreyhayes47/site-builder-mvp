# ISG_Project/internal_site_generator/forms.py
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed # For file uploads
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Email, Length, Regexp, Optional, ValidationError

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class PageTemplateForm(FlaskForm):
    name = StringField('Template Name', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=250)])
    # Added a note about the navbar placeholder in the label for clarity when user is creating/editing templates
    html_content = TextAreaField(
        'HTML Content (Tip: Include for the navbar)', 
        validators=[DataRequired()]
    )
    submit = SubmitField('Save Template')

class WebsiteProjectForm(FlaskForm):
    project_name = StringField('Project Name', validators=[DataRequired(), Length(min=3, max=150)])
    site_title = StringField('Default Site Title', validators=[Optional(), Length(max=100)])
    
    # Theme Colors
    primary_color = StringField('Primary Theme Color (e.g., #RRGGBB)', validators=[
        Optional(), 
        Regexp(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', message='Enter a valid hex color, e.g., #RRGGBB or #RGB')
    ])
    secondary_color = StringField('Secondary Theme Color (e.g., #RRGGBB)', validators=[
        Optional(), 
        Regexp(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', message='Enter a valid hex color, e.g., #RRGGBB or #RGB')
    ])
    accent_color = StringField('Accent Theme Color (e.g., #RRGGBB)', validators=[
        Optional(), 
        Regexp(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', message='Enter a valid hex color, e.g., #RRGGBB or #RGB')
    ])
    
    global_css = TextAreaField('Global Custom CSS', validators=[Optional()])
    favicon = FileField('Favicon (Optional: .ico, .png, .jpg, .jpeg, .svg)', validators=[
        Optional(),
        FileAllowed(['ico', 'png', 'jpg', 'jpeg', 'svg'], 'Allowed favicon types: .ico, .png, .jpg, .jpeg, .svg')
    ])
    submit = SubmitField('Save Project')

# internal_site_generator/forms.py
class ProjectPageForm(FlaskForm):
    title = StringField('Page Title', validators=[DataRequired(), Length(min=1, max=150)])
    slug = StringField('Page Slug (e.g., "about-us")',
                         validators=[
                             DataRequired(),
                             Length(min=1, max=150),
                             Regexp(r'^[a-z0-9]+(?:-[a-z0-9]+)*$',
                                    message="Slug must be lowercase alphanumeric characters, with hyphens for spaces.")
                         ])
    page_template_id = SelectField(
        'Use Template',
        # REMOVE coerce=int
        validators=[DataRequired(message="Please select a template.")] 
    )
    submit = SubmitField('Save Page Settings')

    def validate_page_template_id(self, field):
        # This validator runs after DataRequired.
        # If DataRequired passed, field.data is not empty (so not our placeholder value='').
        if field.data: # Should not be '' if DataRequired passed
            try:
                int(field.data) # Check if it can be an integer
            except ValueError:
                raise ValidationError('Invalid template selection.')
