import re
import requests
from django.db import models
from possem.twitter_utils import get_selfauthed_api_handler, resolve_tco_url

# Create your models here.

def valid_domain ( s ) :
  try :
    requests.get( "http://" + s )
    return True
  except :
    return False

def expand_local_ref ( site, ref ) :
  if ref.startswith( "http" ) :
    return ref

  while ref.startswith( "." ) :
    ref = ref[1:]

  if not ref.startswith( "/" ) :
    ref = "/" + ref

  return site + ref

def splice_string( s, start, chars, insert ) :
  first_part = s[:start]
  last_part  = s[start+chars:]

  return first_part + insert + last_part

def parse_links ( s ) :
  added_length = 0
  for link in re.finditer( "((https?|ftp)://|www\.)[^\s/$.?#].[^\s]*", s ) :
    hyperlink = "<a href=\"" + link.group( 0 ) + "\">" + link.group( 0 ) + "</a>"
    s = splice_string( s, link.start() + added_length, len( link.group( 0 ) ), hyperlink )
    added_length += len( hyperlink ) - len( link.group( 0 ) )
  return s

def parse_tags( s, note = None ) :
  added_length = 0
  for tag in re.finditer( "#([\w-]+)", s ) :
    hyperlink = "<a href=\"/posts?tag=" + tag.group( 1 ) + "\">" + tag.group( 0 ) + "</a>"
    s = splice_string( s, tag.start() + added_length, len( tag.group( 0 ) ), hyperlink )
    added_length += len( hyperlink ) - len( tag.group( 0 ) )

    if note and not tag.group( 1 ) in note.tags :
      note.tags += " " + tag.group( 1 )
  return s

def parse_mentions( s, note = None ) :
  added_length = 0
  twitter_api = get_selfauthed_api_handler( )

  for mention in re.finditer( "@([\w\.-]+)", s ) :
    # If we're actually a reply, link to the replied content
    if note and isinstance( note, Reply ) and mention.group( 1 ) == note.display_name :
      hyperlink = "<a href=\"" + note.profile + "\">" + mention.group( 0 ) + "</a>"

    # TODO: Search contacts (make contacts)

    # If the @-ref is a valid twitter handle, try to pull their website from their profile
    elif not "." in mention.group( 0 ) :
      try :
        user = twitter_api.get_user( mention.group( 1 ) )

        if user.url :
          url = resolve_tco_url( user.url )
        else :
          # Otherwise just link to their twitter profile
          url = "https://twitter.com/" + mention.group( 1 )

        hyperlink = "<a href=\"" + url + "\">" + mention.group( 0 ) + "</a>"
      except Exception as e :
        print e
        continue

    # If the mentioned person is a valid domain anyway, link to that
    elif valid_domain( mention.group( 1 ) ) :
      hyperlink = "<a href=\"http://" + mention.group( 1 ) + "\">" + mention.group( 0 ) + "</a>"

    s = splice_string( s, mention.start() + added_length, len( mention.group( 0 ) ), hyperlink )
    added_length += len( hyperlink ) - len( mention.group( 0 ) )

  return s

class Post ( models.Model ) :
  """
    A post is a media-generic entry on the site. It's meant to be subclassed into various media types.
  """

  date_posted = models.DateTimeField( auto_now_add = True )
  hidden      = models.BooleanField( default = False )
  tags        = models.CharField( max_length = 200, blank = True )

  def kind( self ) :
    try :
      self.note
      try :
        self.note.reply
        return "Reply"
      except AttributeError :
        return "Note"
    except AttributeError :
      try :
        self.article
        return "Article"
      except AttributeError :
        return "Unknown"

  def get_next( self ) :
    if self.kind() == "Article" :
      kind = Article
    else :
      kind = Note

    try :
      return kind.objects.filter( date_posted__gt = self.date_posted ).only( "id" ).earliest( "date_posted" )
    except kind.DoesNotExist :
      return None

  def get_previous( self ) :
    if self.kind() == "Article" :
      kind = Article
    else :
      kind = Note

    try :
      return kind.objects.filter( date_posted__lt = self.date_posted ).only( "id" ).latest( "date_posted" )
    except kind.DoesNotExist :
      return None

  def get_likes( self ) :
    return Like.objects.filter( post_id = self.pk )

  def get_reposts( self ) :
    return Repost.objects.filter( post_id = self.pk )

  def get_comments( self ) :
    return Repost.objects.filter( post_id = self.pk )

  def get_mentions( self ) :
    return Mention.objects.filter( post_id = self.pk )

  def receive_webmention( self, source, target, soup ) :
    anchor = soup.find( href = target )
    if not anchor :
      return

    if anchor.has_key( "rel" ) and anchor['rel'] == "in-reply-to" :
      act = Comment()

      summary = soup.find( "", { "class" : "p-summary" } )
      act.content = summary.text if summary else soup.find( "", { "class" : "e-content" } ).text if soup.find( "", { "class" : "e-content" } ) else None

    elif anchor.has_key( "class" ) and "u-like-of" in anchor['class'] :
      act = Like()

    elif anchor.has_key( "class" ) and "u-repost-of" in anchor['class'] :
      act = Repost()

    else :
      act = Mention()

      pname = soup.find( "", { "class" : "p-name" } )
      act.title = pname.text if pname else source

    if isinstance( act, Comment ) or isinstance( act, Mention ) :
      # Get the mentioner's site and URL
      parts         = source.split( '/' )
      act.site      = parts[2]
      act.site_url  = '/'.join( parts[:3] )

      # Get the mentioner's name and avatar
      hcard = soup.find( "", { "class" : "h-card" } )
      if hcard :
        act.avatar = expand_local_ref( hcard.img['src'], act.site_url )

        if hcard.text :
          act.author = hcard.text
        elif hcard.has_key( "title" ) :
          act.author = hcard['title']
        elif hcard.img.has_key( "alt" ) :
          act.author = hcard.img['alt']
        else :
          act.author = act.site
      else :
        act.author = act.site

      # Get the date it was posted
      date = soup.find( "", { "class" : "dt-published" } )
      act.date_posted = date.text if date else "link to this"
    elif isinstance( act, Like ) or isinstance( act, Repost ) :
      # Get the toplevel URL of the actor
      parts = source.split( '/' )
      act.site_url = '/'.join( parts[:3] )

      # Get the actor's avatar
      hcard = soup.find( "", { "class" : "h-card" } )
      if hcard :
        act.avatar = expand_local_ref( hcard.img['src'], act.site_url )

    act.post    = self
    act.source  = source
    act.save()


class Note ( Post ) :
  """
    A note is a small snippet of text like a tweet.
  """

  content     = models.TextField()
  raw_content = models.TextField( default = "Missing raw data" )

  def __unicode__ ( self ) :
    return self.content[:110]

  def save ( self ) :
    self.raw_content = "<p class=\"note-content e-content p-name\">" + self.content + "</p>"
    
    # Parse out tags
    self.raw_content = parse_tags( self.raw_content, self )

    # Parse out full links
    self.raw_content = parse_links( self.raw_content )

    # Parse out mentions & replies
    self.raw_content = parse_mentions( self.raw_content, self )

    Post.save( self )

class Reply ( Note ) :
  """
    A reply is a special kind of note that replies to some link.
  """

  reply_url     = models.URLField()
  display_name  = models.CharField( max_length = 100, blank = True )
  profile       = models.URLField()

  def save ( self ) :
    if self.display_name and not ("@" + self.display_name) in self.content :
      # The reply target name is not referenced in the post, we'll insert it
      self.content = "@" + self.display_name + " " + self.content

    # Find the "profile" to link to

    # TODO: Search contacts

    # Search silos
    if not "." in self.display_name :
      try :
        twitter_api = get_selfauthed_api_handler( )
        user = twitter_api.get_user( self.display_name )

        if user.url :
          url = resolve_tco_url( user.url )
        else :
          # Otherwise just link to their twitter profile
          url = "https://twitter.com/" + self.display_name

        self.profile = url
      except Exception as e :
        print e
        self.profile = self.reply_url

    # If the display name is a valid domain, that's their profile
    elif valid_domain( self.display_name ) :
      self.profile = "http://" + self.display_name

    # If there's no profile discernable, just make it the target url
    else :
      self.profile = self.reply_url

    Note.save( self )

class Article ( Post ) :
  """
    An article is a large content entry like a blog post.
  """

  title       = models.CharField( max_length = 100 )
  content     = models.TextField()

  def summary( self ) :
    endsummary = self.content.find( "<span class=\"end-summary\"></span>" )
    print( endsummary )
    if endsummary > -1 :
      return self.content[:endsummary]
    else :
      return self.content

  def __unicode__ ( self ) :
    return self.title

class Activity ( models.Model ) :

  post        = models.ForeignKey( Post )
  source      = models.URLField()

class Mention ( Activity ) :

  site        = models.CharField( max_length = 100, blank = True )
  site_url    = models.URLField( blank = True )
  author      = models.CharField( max_length = 100, blank = True )
  avatar      = models.URLField( blank = True )
  title       = models.CharField( max_length = 200, blank = True )
  date_posted = models.CharField( max_length = 100, blank = True )

class Comment ( Activity ) :

  site        = models.CharField( max_length = 100, blank = True )
  site_url    = models.URLField( blank = True )
  author      = models.CharField( max_length = 100, blank = True )
  avatar      = models.URLField( blank = True )
  content     = models.TextField( blank = True )
  date_posted = models.CharField( max_length = 100, blank = True )

class Like ( Activity ) :

  site_url    = models.URLField( null = True )
  avatar      = models.URLField( blank = True )

class Repost ( Activity ) :

  site_url    = models.URLField( null = True )
  avatar      = models.URLField( blank = True )