import logging
import pickle

from collections import defaultdict
from hashlib import sha1

from flask import g
from rdflib.term import URIRef, Variable

from lakesuperior.dictionaries.namespaces import ns_collection as nsc


class Toolbox:
    '''
    Utility class to translate and generate strings and other objects.
    '''

    _logger = logging.getLogger(__name__)

    ROOT_NODE_URN = nsc['fcsystem'].root

    def replace_term_domain(self, term, search, replace):
        '''
        Replace the domain of a term.

        @param term (URIRef) The term (URI) to change.
        @param search (string) Domain string to replace.
        @param replace (string) Domain string to use for replacement.

        @return URIRef
        '''
        s = str(term)
        if s.startswith(search):
            s = s.replace(search, replace)

        return URIRef(s)


    def uuid_to_uri(self, uuid):
        '''Convert a UUID to a URI.

        @return URIRef
        '''
        uri = '{}/{}'.format(g.webroot, uuid) if uuid else g.webroot

        return URIRef(uri)


    def uri_to_uuid(self, uri):
        '''Convert an absolute URI (internal or external) to a UUID.

        @return string
        '''
        if uri == self.ROOT_NODE_URN:
            return None
        elif uri.startswith(nsc['fcres']):
            return str(uri).replace(nsc['fcres'], '')
        else:
            return str(uri).replace(g.webroot, '').strip('/')


    def localize_string(self, s):
        '''Convert URIs into URNs in a string using the application base URI.

        @param string s Input string.

        @return string
        '''
        if s.strip('/') == g.webroot:
            return str(self.ROOT_NODE_URN)
        else:
            return s.strip('/').replace(g.webroot+'/', str(nsc['fcres']))


    def localize_term(self, uri):
        '''
        Convert an URI into an URN.

        @param rdflib.term.URIRef urn Input URI.

        @return rdflib.term.URIRef
        '''
        return URIRef(self.localize_string(str(uri)))


    def localize_graph(self, gr):
        '''
        Locbalize a graph.
        '''
        q = '''
        CONSTRUCT {{ ?s ?p ?o . }} WHERE {{
          {{
            ?s ?p ?o .
            FILTER (
              STRSTARTS(str(?s), "{0}")
              ||
              STRSTARTS(str(?o), "{0}")
              ||
              STRSTARTS(str(?s), "{0}/")
              ||
              STRSTARTS(str(?o), "{0}/")
            ) .
          }}
        }}'''.format(g.webroot)
        flt_gr = gr.query(q)

        for t in flt_gr:
            local_s = self.localize_term(t[0])
            local_o = self.localize_term(t[2]) \
                    if isinstance(t[2], URIRef) \
                    else t[2]
            gr.remove(t)
            gr.add((local_s, t[1], local_o))

        return gr


    def globalize_string(self, s):
        '''Convert URNs into URIs in a string using the application base URI.

        @param string s Input string.

        @return string
        '''
        return s.replace(str(nsc['fcres']), g.webroot + '/')


    def globalize_term(self, urn):
        '''
        Convert an URN into an URI using the application base URI.

        @param rdflib.term.URIRef urn Input URN.

        @return rdflib.term.URIRef
        '''
        if urn == self.ROOT_NODE_URN:
            urn = nsc['fcres']

        return URIRef(self.globalize_string(str(urn)))


    def globalize_graph(self, gr):
        '''
        Globalize a graph.
        '''
        q = '''
        CONSTRUCT {{ ?s ?p ?o . }} WHERE {{
          {{
            ?s ?p ?o .
            FILTER (
              STRSTARTS(str(?s), "{0}")
              ||
              STRSTARTS(str(?o), "{0}")
              ||
              STRSTARTS(str(?s), "{1}")
              ||
              STRSTARTS(str(?o), "{1}")
            ) .
          }}
        }}'''.format(nsc['fcres'], self.ROOT_NODE_URN)
        flt_gr = gr.query(q)

        for t in flt_gr:
            global_s = self.globalize_term(t[0])
            global_o = self.globalize_term(t[2]) \
                    if isinstance(t[2], URIRef) \
                    else t[2]
            gr.remove(t)
            gr.add((global_s, t[1], global_o))

        return gr


    def globalize_rsrc(self, rsrc):
        '''
        Globalize a resource.
        '''
        gr = rsrc.graph
        urn = rsrc.identifier

        global_gr = self.globalize_graph(gr)
        global_uri = self.globalize_term(urn)

        return global_gr.resource(global_uri)


    def parse_rfc7240(self, h_str):
        '''
        Parse `Prefer` header as per https://tools.ietf.org/html/rfc7240

        The `cgi.parse_header` standard method does not work with all possible
        use cases for this header.

        @param h_str (string) The header(s) as a comma-separated list of Prefer
        statements, excluding the `Prefer: ` token.
        '''
        parsed_hdr = defaultdict(dict)

        # Split up headers by comma
        hdr_list = [ x.strip() for x in h_str.split(',') ]
        for hdr in hdr_list:
            parsed_pref = defaultdict(dict)
            # Split up tokens by semicolon
            token_list = [ token.strip() for token in hdr.split(';') ]
            prefer_token = token_list.pop(0).split('=')
            prefer_name = prefer_token[0]
            # If preference has a '=', it has a value, else none.
            if len(prefer_token)>1:
                parsed_pref['value'] = prefer_token[1].strip('"')

            for param_token in token_list:
                # If the token list had a ';' the preference has a parameter.
                print('Param token: {}'.format(param_token))
                param_parts = [ prm.strip().strip('"') \
                        for prm in param_token.split('=') ]
                param_value = param_parts[1] if len(param_parts) > 1 else None
                parsed_pref['parameters'][param_parts[0]] = param_value

            parsed_hdr[prefer_name] = parsed_pref

        return parsed_hdr


    def rdf_cksum(self, gr):
        '''
        Generate a checksum for a graph.

        This is not straightforward because a graph is derived from an
        unordered data structure (RDF).

        What this method does is ordering the graph by subject, predicate,
        object, then creating a pickle string and a checksum of it.

        N.B. The context of the triples is ignored, so isomorphic graphs would
        have the same checksum regardless of the context(s) they are found in.

        @TODO This can be later reworked to use a custom hashing algorithm.

        @param rdflib.Graph gr The graph to be hashed.

        @return string SHA1 checksum.
        '''
        # Remove the messageDigest property, which very likely reflects the
        # previous state of the resource.
        gr.remove((Variable('s'), nsc['premis'].messageDigest, Variable('o')))

        ord_gr = sorted(list(gr), key=lambda x : (x[0], x[1], x[2]))
        hash = sha1(pickle.dumps(ord_gr)).hexdigest()

        return hash

    def split_uuid(self, uuid):
        '''
        Split a UUID into pairtree segments. This mimics FCREPO4 behavior.
        '''
        path = '{}/{}/{}/{}/{}'.format(uuid[:2], uuid[2:4],
                uuid[4:6], uuid[6:8], uuid)

        return path
