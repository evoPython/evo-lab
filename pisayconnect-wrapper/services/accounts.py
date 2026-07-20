def is_parent_username(username):
    return bool(username and username.isdigit())


def is_student_username(username):
    return bool(username and not username.isdigit())
