from copy import deepcopy

import arrow

from rdflib import Graph
from rdflib.namespace import RDF, XSD
from rdflib.query import ResultException
from rdflib.resource import Resource
from rdflib.term import Literal, URIRef, Variable

from lakesuperior.dictionaries.namespaces import ns_collection as nsc
from lakesuperior.dictionaries.namespaces import ns_mgr as nsm
from lakesuperior.dictionaries.srv_mgd_terms import  srv_mgd_subjects, \
        srv_mgd_predicates, srv_mgd_types
from lakesuperior.exceptions import InvalidResourceError, \
        ResourceNotExistsError, TombstoneError
from lakesuperior.store_layouts.rdf.base_rdf_layout import BaseRdfLayout
from lakesuperior.toolbox import Toolbox


class SimpleLayout(BaseRdfLayout):
    '''
    This is the simplest layout.

    It uses a flat triple structure without named graphs aimed at performance.

    Changes are destructive.

    In theory it could be used on top of a triplestore instead of a quad-store
    for (possible) improved speed and reduced storage.
    '''

    def extract_imr(self, uri, strict=False, incl_inbound=False,
                incl_children=True, embed_children=False, incl_srv_mgd=True):
        '''
        See base_rdf_layout.extract_imr.
        '''
        inbound_construct = '\n?s1 ?p1 ?s .' if incl_inbound else ''
        inbound_qry = '\nOPTIONAL { ?s1 ?p1 ?s . } .' if incl_inbound else ''

        # Include and/or embed children.
        embed_children_trp = embed_children_qry = ''
        if incl_srv_mgd and incl_children:
            incl_children_qry = ''

            # Embed children.
            if embed_children:
                embed_children_trp = '?c ?cp ?co .'
                embed_children_qry = '''
                OPTIONAL {{
                  ?s ldp:contains ?c .
                  {}
                }}
                '''.format(embed_children_trp)
        else:
            incl_children_qry = '\nFILTER ( ?p != ldp:contains )' \

        q = '''
        CONSTRUCT {{
            ?s ?p ?o .{inb_cnst}
            {embed_chld_t}
        }} WHERE {{
            ?s ?p ?o .{inb_qry}{incl_chld}{embed_chld}
        }}
        '''.format(inb_cnst=inbound_construct,
                inb_qry=inbound_qry, incl_chld=incl_children_qry,
                embed_chld_t=embed_children_trp, embed_chld=embed_children_qry)

        try:
            qres = self._conn.query(q, initBindings={'s' : uri})
        except ResultException:
            # RDFlib bug: https://github.com/RDFLib/rdflib/issues/775
            g = Graph()
        else:
            g = qres.graph

        #self._logger.debug('Found resource: {}'.format(
        #        g.serialize(format='turtle').decode('utf-8')))
        if strict and not len(g):
            raise ResourceNotExistsError(uri)

        rsrc = Resource(g, uri)

        # Check if resource is a tombstone.
        if rsrc[RDF.type : nsc['fcsystem'].Tombstone]:
            raise TombstoneError(
                    Toolbox().uri_to_uuid(rsrc.identifier),
                    rsrc.value(nsc['fcrepo'].created))
        elif rsrc.value(nsc['fcsystem'].tombstone):
            raise TombstoneError(
                    Toolbox().uri_to_uuid(
                            rsrc.value(nsc['fcsystem'].tombstone).identifier),
                    tombstone_rsrc.value(nsc['fcrepo'].created))

        return rsrc


    def ask_rsrc_exists(self, urn):
        '''
        See base_rdf_layout.ask_rsrc_exists.
        '''
        self._logger.info('Checking if resource exists: {}'.format(urn))

        return self._conn.query('ASK { ?s ?p ?o . }', initBindings={
            's' : urn})


    def create_rsrc(self, imr):
        '''
        See base_rdf_layout.create_rsrc.
        '''
        self._logger.debug('Creating resource:\n{}'.format(
            imr.graph.serialize(format='turtle').decode('utf8')))
        #self.ds |= imr.graph # This does not seem to work with datasets.
        for t in imr.graph:
            self.ds.add(t)

        return self.RES_CREATED


    def replace_rsrc(self, imr):
        '''
        See base_rdf_layout.replace_rsrc.
        '''
        rsrc = self.rsrc(imr.identifier)

        # Delete the stored triples but spare the protected predicates.
        del_trp_qry = []
        for p in rsrc.predicates():
            if p.identifier not in self.protected_pred:
                self._logger.debug('Removing {}'.format(p.identifier))
                rsrc.remove(p.identifier)
            else:
                self._logger.debug('NOT Removing {}'.format(p))
                imr.remove(p.identifier)

        #self.ds |= imr.graph # This does not seem to work with datasets.
        for t in imr.graph:
            self.ds.add(t)

        return self.RES_UPDATED


    def modify_dataset(self, remove_trp, add_trp):
        '''
        See base_rdf_layout.update_rsrc.
        '''
        self._logger.debug('Remove triples: {}'.format(
                remove_trp.serialize(format='turtle').decode('utf-8')))
        self._logger.debug('Add triples: {}'.format(
                add_trp.serialize(format='turtle').decode('utf-8')))

        for t in remove_trp:
            self.ds.remove(t)
        for t in add_trp:
            self.ds.add(t)


    ## PROTECTED METHODS ##

    def _do_delete_rsrc(self, rsrc, inbound):
        '''
        See BaseRdfLayout._do_delete_rsrc
        '''
        urn = rsrc.identifier
        print('Removing resource {}.'.format(urn))

        rsrc.remove(Variable('p'))

        if inbound:
            self.ds.remove((Variable('s'), Variable('p'), rsrc.identifier))

        return urn


    def leave_tombstone(self, urn, parent_urn=None):
        '''
        See BaseRdfLayout.leave_tombstone
        '''
        if parent_urn:
            self.ds.add((urn, nsc['fcsystem'].tombstone, parent_urn))
        else:
            # @TODO Use gunicorn to get request timestamp.
            ts = Literal(arrow.utcnow(), datatype=XSD.dateTime)
            self.ds.add((urn, RDF.type, nsc['fcsystem'].Tombstone))
            self.ds.add((urn, nsc['fcrepo'].created, ts))


    def delete_tombstone(self, urn):
        '''
        See BaseRdfLayout.leave_tombstone
        '''
        self.ds.remove((urn, RDF.type, nsc['fcsystem'].Tombstone))
        self.ds.remove((urn, nsc['fcrepo'].created, None))
        self.ds.remove((None, nsc['fcsystem'].tombstone, urn))

