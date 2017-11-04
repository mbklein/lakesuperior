import logging

from collections import defaultdict
from uuid import uuid4

from flask import Blueprint, request
from werkzeug.datastructures import FileStorage

from lakesuperior.exceptions import InvalidResourceError, \
        ResourceExistsError, ResourceNotExistsError, \
        InvalidResourceError, ServerManagedTermError
from lakesuperior.model.ldp_rs import Ldpc, LdpRs
from lakesuperior.model.ldp_nr import LdpNr
from lakesuperior.store_layouts.rdf.base_rdf_layout import BaseRdfLayout
from lakesuperior.util.translator import Translator


logger = logging.getLogger(__name__)


# Blueprint for LDP REST API. This is what is usually found under `/rest/` in
# standard fcrepo4. Here, it is under `/ldp` but initially `/rest` can be kept
# for backward compatibility.

ldp = Blueprint('ldp', __name__)

accept_patch = (
    'application/sparql-update',
)
accept_post_rdf = (
    'application/ld+json',
    'application/n-triples',
    'application/rdf+xml',
    #'application/x-turtle',
    #'application/xhtml+xml',
    #'application/xml',
    #'text/html',
    'text/n3',
    #'text/plain',
    'text/rdf+n3',
    'text/turtle',
)
#allow = (
#    'COPY',
#    'DELETE',
#    'GET',
#    'HEAD',
#    'MOVE',
#    'OPTIONS',
#    'PATCH',
#    'POST',
#    'PUT',
#)

std_headers = {
    'Accept-Patch' : ','.join(accept_patch),
    'Accept-Post' : ','.join(accept_post_rdf),
    #'Allow' : ','.join(allow),
}

## REST SERVICES ##

@ldp.route('/<path:uuid>', methods=['GET'])
@ldp.route('/', defaults={'uuid': None}, methods=['GET'],
        strict_slashes=False)
def get_resource(uuid):
    '''
    Retrieve RDF or binary content.
    '''
    out_headers = std_headers

    pref_return = defaultdict(dict)
    if 'prefer' in request.headers:
        prefer = Translator.parse_rfc7240(request.headers['prefer'])
        logger.debug('Parsed Prefer header: {}'.format(prefer))
        if 'return' in prefer:
            pref_return = prefer['return']

    # @TODO Add conditions for LDP-NR
    rsrc = Ldpc(uuid)
    try:
        out = rsrc.get(pref_return=pref_return)
    except ResourceNotExistsError:
        return 'Resource #{} not found.'.format(rsrc.uuid), 404
    else:
        out_headers = rsrc.head()
        return (out.graph.serialize(format='turtle'), out_headers)


@ldp.route('/<path:parent>', methods=['POST'])
@ldp.route('/', defaults={'parent': None}, methods=['POST'],
        strict_slashes=False)
def post_resource(parent):
    '''
    Add a new resource in a new URI.
    '''
    out_headers = std_headers
    try:
        slug = request.headers['Slug']
    except KeyError:
        slug = None

    cls, data = class_from_req_body()

    try:
       rsrc = cls.inst_for_post(parent, slug)
    except ResourceNotExistsError as e:
        return str(e), 404
    except InvalidResourceError as e:
        return str(e), 409

    try:
        rsrc.post(data)
    except ServerManagedTermError as e:
        return str(e), 412

    out_headers.update({
        'Location' : rsrc.uri,
    })

    return rsrc.uri, out_headers, 201


@ldp.route('/<path:uuid>', methods=['PUT'])
def put_resource(uuid):
    '''
    Add a new resource at a specified URI.
    '''
    logger.info('Request headers: {}'.format(request.headers))
    rsp_headers = std_headers

    cls, data = class_from_req_body()

    rsrc = cls(uuid)

    logger.debug('form: {}'.format(request.form))
    # Parse headers.
    pref_handling = None
    if 'prefer' in request.headers:
        prefer = Translator.parse_rfc7240(request.headers['prefer'])
        logger.debug('Parsed Prefer header: {}'.format(prefer))
        if 'handling' in prefer:
            pref_handling = prefer['handling']['value']

    try:
        ret = rsrc.put(
            request.get_data().decode('utf-8'),
            handling=pref_handling
        )
    except InvalidResourceError as e:
        return str(e), 409
    except ResourceExistsError as e:
        return str(e), 409
    except ServerManagedTermError as e:
        return str(e), 412
    else:
        res_code = 201 if ret == BaseRdfLayout.RES_CREATED else 204
        return '', res_code, rsp_headers


@ldp.route('/<path:uuid>', methods=['PATCH'])
def patch_resource(uuid):
    '''
    Update an existing resource with a SPARQL-UPDATE payload.
    '''
    headers = std_headers
    rsrc = Ldpc(uuid)

    try:
        rsrc.patch(request.get_data().decode('utf-8'))
    except ResourceNotExistsError:
        return 'Resource #{} not found.'.format(rsrc.uuid), 404
    except ServerManagedTermError as e:
        return str(e), 412

    return '', 204, headers


@ldp.route('/<path:uuid>', methods=['DELETE'])
def delete_resource(uuid):
    '''
    Delete a resource.
    '''
    headers = std_headers
    rsrc = Ldpc(uuid)

    try:
        rsrc.delete()
    except ResourceNotExistsError:
        return 'Resource #{} not found.'.format(rsrc.uuid), 404

    return '', 204, headers


def class_from_req_body():
    logger.debug('Content type: {}'.format(request.mimetype))
    #logger.debug('files: {}'.format(request.files))
    logger.debug('stream: {}'.format(request.stream))
    if request.mimetype in accept_post_rdf:
        cls = Ldpc
        # Parse out the RDF string.
        data = request.data.decode('utf-8')
    else:
        cls = LdpNr
        if request.mimetype == 'multipart/form-data':
            # This seems the "right" way to upload a binary file, with a
            # multipart/form-data MIME type and the file in the `file` field.
            # This however is not supported by FCREPO4.
            data = request.files.get('file').stream
        else:
            # This is a less clean way, with the file in the form body and the
            # request as application/x-www-form-urlencoded.
            # This is how FCREPO4 accepts binary uploads.
            data = request.stream

    logger.info('POSTing resource of type: {}'.format(cls.__name__))
    #logger.info('POST data: {}'.format(data))

    return cls, data


