''' Put all exceptions here. '''

class ResourceError(RuntimeError):
    '''
    Raised in an attempt to create a resource a URI that already exists and is
    not supposed to.

    This usually surfaces at the HTTP level as a 409.
    '''
    def __init__(self, uuid, msg=None):
        self.uuid = uuid
        self.msg = msg


class ResourceExistsError(ResourceError):
    '''
    Raised in an attempt to create a resource a URI that already exists and is
    not supposed to.

    This usually surfaces at the HTTP level as a 409.
    '''
    def __repr__(self):
        return self.msg or 'Resource #{} already exists.'.format(self.uuid)



class ResourceNotExistsError(ResourceError):
    '''
    Raised in an attempt to create a resource a URN that does not exist and is
    supposed to.

    This usually surfaces at the HTTP level as a 404.
    '''
    def __repr__(self):
        return self.msg or 'Resource #{} does not exist.'.format(self.uuid)



class InvalidResourceError(ResourceError):
    '''
    Raised when an invalid resource is found.

    This usually surfaces at the HTTP level as a 409 or other error.
    '''
    def __repr__(self):
        return self.msg or 'Resource #{} is invalid.'.format(self.uuid)



class ServerManagedTermError(RuntimeError):
    '''
    Raised in an attempt to change a triple containing a server-managed term.

    This usually surfaces at the HTTP level as a 409 or other error.
    '''
    def __init__(self, terms, term_type):
        if term_type == 's':
            term_name = 'subject'
        elif term_type == 'p':
            term_name = 'predicate'
        elif term_type == 't':
            term_name = 'RDF type'
        else:
            term_name = 'term'

        self.terms = terms
        self.term_name = term_name

    def __str__(self):
        return 'Some {}s are server managed and cannot be modified: {}'\
                .format(self.term_name, ' , '.join(self.terms))


class SingleSubjectError(RuntimeError):
    '''
    Raised when a SPARQL-Update query or a RDF payload for a PUT contain
    subjects that do not correspond to the resource being operated on.
    '''
    def __init__(self, uri, subject):
        self.uri = uri
        self.subject = subject

    def __str__(self):
        return '{} is not in the topic of this RDF, which is {}'.format(
                self.uri, self.subject)

