"""Add theme colors and update project/navbar relationships

Revision ID: d065863569a3
Revises: 8468e50371a2
Create Date: 2025-05-15 13:15:03.378352

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd065863569a3'
down_revision = '8468e50371a2'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('navbar_item', schema=None) as batch_op:
        batch_op.alter_column('project_page_id',
               existing_type=sa.INTEGER(),
               nullable=False)

    with op.batch_alter_table('website_project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('primary_color', sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column('secondary_color', sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column('accent_color', sa.String(length=7), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('website_project', schema=None) as batch_op:
        batch_op.drop_column('accent_color')
        batch_op.drop_column('secondary_color')
        batch_op.drop_column('primary_color')

    with op.batch_alter_table('navbar_item', schema=None) as batch_op:
        batch_op.alter_column('project_page_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    # ### end Alembic commands ###
